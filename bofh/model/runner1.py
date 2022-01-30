from asyncio import get_event_loop
from random import choice
from time import sleep

from jsonrpc_websocket import Server

from bofh.utils.misc import progress_printer, LogAdapter,Timer
from bofh.utils.web3 import Web3Connector, Web3PoolExecutor, JSONRPCConnector, method_id, log_topic_id, parse_data_parameters


__doc__="""Start model runner.

Usage: bofh.model.runner1 [options]

Options:
  -h  --help
  -d, --dsn=<connection_str>            DB dsn connection string [default: sqlite3://status.db]
  -c, --connection_url=<url>            Web3 RPC connection URL [default: %s]
  -n <n>                                number of pools to query before exit (benchmark mode)
  -j <n>                                number of RPC data ingest workers, default one per hardware thread. Only used during initialization phase
  -v, --verbose                         debug output
  --chunk_size=<n>                      preloaded work chunk size per each worker [default: 100]
  --pred_polling_interval=<n>           Web3 prediction polling internal in millisecs [default: 1000]
  --swap_log_db_dsn=<connection_str>    Prediction log swaps DB dsn connection string [default: none]
  --start_token_address=<address>       on-chain address of start token [default: WBNB]
  --cli                                 preload status and stop at CLI (for debugging)
""" % (Web3Connector.DEFAULT_URI_WSRPC, )

from dataclasses import dataclass
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB, StatusScopedCursor, SwapLogScopedCursor
from bofh_model_ext import TheGraph, log_level, log_register_sink, log_set_level, PathEvalutionConstraints


PREDICTION_LOG_TOPIC0_SWAP = log_topic_id("Swap(address,uint256,uint256,uint256,uint256,address)")
PREDICTION_LOG_TOPIC0_SYNC = log_topic_id("Sync(uint112,uint112)")
WBNB_address = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c" # id=2
TETHER_address = "0x55d398326f99059ff775485246999027b3197955" # id=4
START_TOKEN = WBNB_address


@dataclass
class Args:
    status_db_dsn: str = None
    verbose: bool = False
    pools_limit: int = 0
    web3_rpc_url: str = None
    max_workers: int = 0
    chunk_size: int = 0
    pred_polling_interval: int = 0
    swap_log_db_dsn: str = None
    start_token_address: str = None
    cli: bool = False

    @staticmethod
    def default(arg, d, suppress_list=None):
        if suppress_list and arg in suppress_list:
            arg = None
        if arg: return arg
        return d

    @classmethod
    def from_cmdline(cls, docstr):
        from docopt import docopt
        args = docopt(docstr)
        return cls(
            status_db_dsn = args["--dsn"]
            , verbose=bool(cls.default(args["--verbose"], 0))
            , pools_limit=int(cls.default(args["-n"], 0))
            , web3_rpc_url=cls.default(args["--connection_url"], 0)
            , max_workers=int(cls.default(args["-j"], 0))
            , chunk_size=int(cls.default(args["--chunk_size"], 100))
            , pred_polling_interval=int(cls.default(args["--pred_polling_interval"], 1000))
            , swap_log_db_dsn=cls.default(args["--swap_log_db_dsn"], None, suppress_list=["none"])
            , start_token_address=cls.default(args["--start_token_address"], START_TOKEN, suppress_list=["WBNB"])
            , cli=bool(cls.default(args["--cli"], 0))
        )


def getReserves(pool_address):
    """Invoke local execution of PoolContract.getReserves() on the EVM for the specified pool.
       Returns a tuple of (pool_address, reserve0, reserve1).

       This function is meant to be executed across an IPC multiprocess turk for massive parallelism.

       It reuses its web3 connection and assets to improve batch performance.

       It also avoids usage of the web3 framework which has shown flaky performances in the past. It does
       the dirty handling inline, and calls a remote RPC at the lowest possible level."""
    try:
        exe = getReserves.exe
        ioloop = getReserves.ioloop
        mid = getReserves.mid
    except AttributeError:
        exe = getReserves.exe = JSONRPCConnector.get_connection()
        ioloop = getReserves.ioloop = get_event_loop()
        mid = getReserves.mid = method_id("getReserves()")
    for i in range(4):  # make two attempts
        fut = exe.eth_call({"to": pool_address, "data": mid}, "latest")
        res = ioloop.run_until_complete(fut)
        # at this point "res" should be a long 0xhhhhh... byte hexstring.
        # it should be composed of 3 32-bytes big-endian values. In sequence:
        # - reserve0
        # - reserve1
        # - blockTimestampLast (mod 2**32) of the last block during which an interaction occured for the pair.
        try:
            reserve0, reserve1, blockTimestampLast = parse_data_parameters(res)
            return (pool_address
                    , reserve0
                    , reserve1
                    , blockTimestampLast
                    )
        except:
            pass
        print("invalid response (expected 96-byte hexstring):", res)
        return pool_address, None, None, None


class Runner:
    log = getLogger(__name__)

    def __init__(self, args: Args):
        self.graph = TheGraph()
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        self.swap_log_db = None
        if self.args.swap_log_db_dsn:
            self.swap_log_db = ModelDB(schema_name="swap_log", cursor_factory=SwapLogScopedCursor, db_dsn=self.args.swap_log_db_dsn)
            self.swap_log_db.open_and_priming()
        self.pools = set()
        self.ioloop = get_event_loop()
        # self.polling_started = Event()

    @property
    def pools_ctr(self):
        return len(self.pools)

    @staticmethod
    def random_address():
        res = "0x"
        hex = "0123456789abcdef"
        for i in range(40):
            res += choice(hex)
        return res

    def preload_exchanges(self):
        self.log.info("preloading exchanges...")
        ctr = 0
        with self.db as curs:
            for id, name in curs.list_exchanges():
                exc = self.graph.add_exchange(id, self.random_address(), name)
                assert exc is not None
                ctr += 1
        self.log.info("EXCHANGE set loaded, size is %r items", ctr)

    def preload_tokens(self):
        with self.db as curs:
            ctr = curs.count_tokens()
            print_progress = progress_printer(ctr, "preloading tokens {percent}% ({count} of {tot}"
                                              " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                              , on_same_line=True)
            with print_progress:
                for args in curs.list_tokens():
                    tok = self.graph.add_token(*args)
                    if tok is None:
                        raise RuntimeError("integrity error: token address is already not of a token: id=%r, %r" % (id, args))
                    print_progress()
            self.log.info("TOKENS set loaded, size is %r items", print_progress.ctr)

    def preload_pools(self):
        with self.db as curs:
            ctr = curs.count_pools()
            print_progress = progress_printer(ctr, "preloading pools {percent}% ({count} of {tot}"
                                              " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                              , on_same_line=True)
            with print_progress:
                for id, address, exchange_id, token0_id, token1_id in curs.list_pools():
                    t0 = self.graph.lookup_token(token0_id)
                    t1 = self.graph.lookup_token(token1_id)
                    if not t0 or not t1:
                        if self.args.verbose:
                            self.log.warning("disabling pool %s due to missing or disabled affering token "
                                             "(token0=%r, token1=%r)", address, token0_id, token1_id)
                        continue
                    exchange = self.graph.lookup_exchange(exchange_id)
                    assert exchange is not None
                    pool = self.graph.add_lp(id, address, exchange, t0, t1)
                    print_progress()
                    if pool is None:
                        if self.args.verbose:
                            self.log.warning("integrity error: pool address is already not of a pool: "
                                             "id=%r, %r", id, address)
                        continue
                    self.pools.add(pool)
                    if self.args.pools_limit and print_progress.ctr >= self.args.pools_limit:
                        self.log.info("stopping after loading %r pools, "
                                      "as per effect of -n cli parameter", print_progress.ctr)
                        break
            self.log.info("POOLS set loaded, size is %r items", print_progress.ctr)
            missing = print_progress.tot - print_progress.ctr
            if missing > 0:
                self.log.info("  \\__ %r over pool the total %r were not loaded due to "
                              "failed graph connectivity or other problems", missing, print_progress.tot)

    def preload_balances(self):
        self.log.info("fetching balances via Web3...")
        print_progress = progress_printer(self.pools_ctr
                                          , "fetching pool reserves {percent}% ({count} of {tot}"
                                            " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                          , on_same_line=True)
        with Web3PoolExecutor(connection_uri=self.args.web3_rpc_url, max_workers=self.args.max_workers) as executor:
            self.log.info("fetching balances via Web3:"
                     "\n\t- %r pool getReserve requests"
                     "\n\t- on Web3 servant at %s"
                     "\n\t- using %d workers"
                     "\n\t- each with a %d preload queue"
                      , self.pools_ctr
                      , self.args.web3_rpc_url
                      , self.args.max_workers
                      , self.args.chunk_size
                      )
            curs = None
            if self.swap_log_db:
                curs = self.swap_log_db.cursor()
            try:
                def pool_addresses_iter():
                    for p in self.pools:
                        yield str(p.address)
                for pool_addr, reserve0, reserve1, blockTimestampLast in executor.map(getReserves, pool_addresses_iter(), chunksize=self.args.chunk_size):
                    try:
                        if reserve0 is None or reserve1 is None:
                            continue
                        pair = self.graph.lookup_lp(pool_addr)
                        if not pair:
                            raise IndexError("unknown pool: %s" % pool_addr)
                        # reset pool reserves
                        pair.setReserves(reserve0, reserve1)
                        if curs:
                            pool = self.graph.lookup_lp(pool_addr)
                            assert pool
                            curs.add_pool_reserve(pool.tag, reserve0, reserve1)
                        print_progress()
                    except:
                        self.log.exception("unable to query pool %s", pool_addr)
            finally:
                if self.swap_log_db:
                    self.swap_log_db.commit()
            executor.shutdown(wait=True)

    def preload_balances_from_db(self):
        assert self.swap_log_db

        self.log.info("fetching balances previously saved in db...")
        with self.swap_log_db as curs:
            nr = curs.execute("SELECT COUNT(1) FROM pool_reserves").get_int()
            with progress_printer(nr, "fetching pool reserves {percent}% ({count} of {tot}"
                                       " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                       , on_same_line=True) as print_progress:

                ok = 0
                disc = 0
                for poolid, reserve0, reserve1 in curs.execute("SELECT pool, reserve0, reserve1 FROM pool_reserves").get_all():
                    pool = self.graph.lookup_lp(poolid)
                    print_progress()
                    if not pool:
                        if self.args.verbose:
                            self.log.debug("pool id not found: %r", poolid)
                        disc += 1
                        continue
                    pool.setReserves(reserve0, reserve1)
                    ok += 1
                self.log.info("%r records read, reserves loaded for %r pools, %r discarded"
                              , print_progress.ctr, ok, disc)

    def __serve_eth_consPredictLogs(self, result):
        if result and result.get("logs"):
            blockNumber = result["blockNumber"]
            if blockNumber > self.latestBlockNumber:
                self.latestBlockNumber = blockNumber
                self.log.info("block %r, found %r log predictions" % (self.latestBlockNumber, len(result["logs"])))
                for log in result["logs"]:
                    pool_addr = log["address"]
                    if not pool_addr:
                        continue
                    pool = self.graph.lookup_lp(pool_addr)
                    if not pool:
                        if self.args.verbose:
                            self.log.info("unknown pool of interest: %s", pool_addr)
                        continue
                    self.log.info("pool of interest: %s", pool_addr)
                    continue
                    try:
                        amount0In, amount1In, amount0Out, amount1Out = parse_data_parameters(log["data"])
                    except:
                        self.log.exception("unable to decode swap log data")
                        continue
                    try:
                        if amount0In > 0 and amount1In > 0:
                            raise RuntimeError("inconsistent swap. Should not be possible: "
                                               "amount0In > 0 and amount1In > 0 (%r, %r)" %
                                               (amount0In, amount1In))
                        if amount0Out > 0 and amount1Out > 0:
                            raise RuntimeError(
                                "inconsistent swap. Should not be possible: amount0Out > 0 and amount1Out > 0 (%r, %r)" %
                                (amount0Out, amount1Out))
                        checks_out = False
                        if amount0In > 0:
                            if amount1Out == 0:
                                raise RuntimeError(
                                    "inconsistent swap. amount0In > 0 but amount1Out == 0 (%r, %r)" %
                                    (amount0In, amount1Out))
                            tokenIn = pool.token0
                            tokenOut = pool.token1
                            balanceIn = amount0In
                            balanceOut = amount1Out
                            reserveInBefore = int(str(pool.reserve0))
                            reserveOutBefore = int(str(pool.reserve1))
                            checks_out = True

                        if amount1In > 0:
                            if amount0Out == 0:
                                raise RuntimeError(
                                    "inconsistent swap. amount1In > 0 but amount0Out == 0 (%r, %r)" %
                                    (amount1In, amount0Out))
                            tokenIn = pool.token1
                            tokenOut = pool.token0
                            balanceIn = amount1In
                            balanceOut = amount0Out
                            reserveInBefore = int(str(pool.reserve1))
                            reserveOutBefore = int(str(pool.reserve0))
                            checks_out = True
                        if checks_out:
                            reserveInAfter = reserveInBefore + balanceIn
                            reserveOutAfter = reserveOutBefore - balanceOut
                            reserveInPctGain = (100 * balanceIn) / reserveInBefore
                            reserveOutPctLoss = (100 * balanceOut) / reserveOutBefore
                            rate = balanceOut / balanceIn
                            self.log.info("pool %s swaps %r %s toward %r %s, "
                                          "effective %s/%s swap rate is %02.05f, "
                                          "reserves changed from %r/%r to %r/%r, "
                                          "this swap affects %02.10f%% of the stored liquidity"
                                          , pool_addr, balanceIn, tokenIn.address, balanceOut, tokenOut.address
                                          , tokenIn.address, tokenOut.address, rate
                                          , reserveInBefore, reserveOutBefore, reserveInAfter, reserveOutAfter
                                          , reserveInPctGain)
                            if self.swap_log_db:
                                with self.swap_log_db as curs:
                                    curs.add_swap_log(
                                        block_nr=self.latestBlockNumber
                                        , json_data=log
                                        , pool_id=pool.tag
                                        , tokenIn=tokenIn.tag
                                        , tokenOut=tokenIn.tag
                                        , poolAddr=str(pool.address)
                                        , tokenInAddr=str(tokenIn.address)
                                        , tokenOutAddr=str(tokenOut.address)
                                        , balanceIn=balanceIn
                                        , balanceOut=balanceOut
                                        , reserveInBefore=reserveInBefore
                                        , reserveOutBefore=reserveOutBefore
                                    )
                        else:
                            self.log.warning("swap parameters don't check out. ignored")

                    except:
                        self.log.exception("unexpected swap data. check this out")
                        continue

    async def prediction_polling_task(self):
        # await self.polling_started.wait()
        constraint = PathEvalutionConstraints()
        constraint.initial_token_wei_balance = self.graph.start_token.toWei(1)
        log_set_level(log_level.info)
        self.latestBlockNumber = 0

        server = Server(self.args.web3_rpc_url)
        try:
            await server.ws_connect()
            while True:  # self.polling_started.is_set():
                try:
                    result = await server.eth_consPredictLogs(0, 0, PREDICTION_LOG_TOPIC0_SYNC, PREDICTION_LOG_TOPIC0_SWAP)
                    blockNumber = result["blockNumber"]
                    if blockNumber <= self.latestBlockNumber:
                        continue
                    self.latestBlockNumber = blockNumber
                except:
                    self.log.exception("Error during eth_consPredictLogs() RPC execution")
                    continue
                try:
                    try:
                        self.digest_prediction_payload(result)
                    except:
                        self.log.exception("Error during parsing of eth_consPredictLogs() results")
                    try:
                        self.graph.evaluate_paths_of_interest(constraint)
                    except:
                        self.log.exception("Error during execution of TheGraph::evaluate_paths_of_interest()")
                finally:
                    # forget about predicted states. go back to normal
                    self.graph.clear_lp_of_interest()

                sleep(self.args.pred_polling_interval * 0.001)
        except:
            self.log.exception("Error in prediction polling thread")
        finally:
            await server.close()

    def poll_prediction(self):
        self.ioloop.run_until_complete(self.prediction_polling_task())

    def digest_prediction_payload(self, payload):
        assert isinstance(payload, dict)
        logs = payload["logs"]
        if not logs:
            return
        for log in logs:
            address = log["address"]
            if not address:
                continue
            pool = self.graph.lookup_lp(address)
            if not pool:
                if self.args.verbose:
                    self.log.debug("unknown pool of interest: %s", address)
                continue
            topic0 = log["topic0"]
            if topic0 == PREDICTION_LOG_TOPIC0_SYNC:
                data = log["data"]
                try:
                    r0, r1 = parse_data_parameters(data)
                except:
                    self.log.exception("unable to decode sync log data")
                    continue
                if self.args.verbose:
                    self.log.info("use Sync event to update reserves of pool %r: %s(%s-%s), reserve=%r, reserve1=%r"
                                   , address
                                   , pool.exchange.name
                                   , pool.token0.symbol
                                   , pool.token1.symbol
                                   , r0
                                   , r1)
                pool.setReserves(r0, r1)
                continue
            if topic0 == PREDICTION_LOG_TOPIC0_SWAP:
                data = log["data"]
                try:
                    amount0In, amount1In, amount0Out, amount1Out = parse_data_parameters(data)
                except:
                    self.log.exception("unable to decode swap log data")
                    continue
                if self.args.verbose:
                    self.log.info("pool %r: %s(%s-%s) entering predicted state "
                                   "(amount0In=%r, amount1In=%r, amount0Out=%r, amount1Out=%r)"
                                   , address
                                   , pool.exchange.name
                                   , pool.token0.symbol
                                   , pool.token1.symbol
                                   , amount0In, amount1In, amount0Out, amount1Out
                                   )
                pool.enter_predicted_state(amount0In, amount1In, amount0Out, amount1Out)
                self.graph.add_lp_of_interest(pool)
                continue




def main():
    basicConfig(level="INFO")
    log_set_level(log_level.debug)
    log_register_sink(LogAdapter(level="DEBUG"))
    args = Args.from_cmdline(__doc__)
    runner = Runner(args)
    runner.preload_exchanges()
    runner.preload_tokens()
    start_token = runner.graph.lookup_token(args.start_token_address)
    assert start_token
    runner.graph.start_token = start_token
    runner.preload_pools()
    while args.cli:
        from IPython import embed
        embed()
    runner.graph.calculate_paths()
    runner.preload_balances()
    print("LOAD COMPLETE")
    runner.poll_prediction()
    while True:
        sleep(10)


if __name__ == '__main__':
    main()