from asyncio import get_event_loop
from random import choice
from time import sleep

from jsonrpc_websocket import Server

from bofh.utils.misc import progress_printer
from bofh.utils.web3 import Web3Connector, Web3PoolExecutor, JSONRPCConnector, method_id, parse_data_parameters

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
""" % Web3Connector.DEFAULT_URI_WSRPC

from dataclasses import dataclass
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB, StatusScopedCursor, SwapLogScopedCursor
from bofh_model_ext import TheGraph, log_level, log_register_sink, log_set_level


PREDICTION_LOG_TOPIC0 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"  # Keccak256("Swap(address,uint256,uint256,uint256,uint256,address)")
WBNB_address = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
TETHER_address = "0x55d398326f99059ff775485246999027b3197955"
START_TOKEN = TETHER_address

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
        self.skip = 0
        self.tot = 0
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
        with self.db as curs:
            for id, name in curs.list_exchanges():
                exc = self.graph.add_exchange(id, self.random_address(), name)
                assert exc is not None

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
                        self.skip += 1
                        if self.args.verbose:
                            self.log.warning("disabling pool %s due to missing or disabled affering token "
                                             "(token0=%r, token1=%r)", address, token0_id, token1_id)
                        continue
                    exchange = self.graph.lookup_exchange(exchange_id)
                    assert exchange is not None
                    pool = self.graph.add_lp(id, address, exchange, t0, t1)
                    print_progress()
                    self.tot += 1
                    if pool is None:
                        self.skip += 1
                        if self.args.verbose:
                            self.log.warning("integrity error: pool address is already not of a pool: "
                                             "id=%r, %r -- skip %r over %r", id, address, self.skip, self.tot)
                        continue
                    self.pools.add(pool)
                    if self.args.pools_limit and self.pools_ctr >= self.args.pools_limit:
                        self.log.info("stopping after loading %r pools, as per effect of -n cli parameter", self.pools_ctr)
                        break

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
                        pair.reserve0, pair.reserve1 = reserve0, reserve1
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
        server = Server(self.args.web3_rpc_url)
        self.latestBlockNumber = 0
        try:
            await server.ws_connect()
            while True:  # self.polling_started.is_set():
                try:
                    result = await server.eth_consPredictLogs(0, 0, PREDICTION_LOG_TOPIC0)
                except:
                    self.log.exception("Error during eth_consPredictLogs() RPC execution")
                    continue
                try:
                    self.__serve_eth_consPredictLogs(result)
                except:
                    self.log.exception("Error during parsing of eth_consPredictLogs() results")

                sleep(self.args.pred_polling_interval * 0.001)
        except:
            self.log.exception("Error in prediction polling thread")
        finally:
            await server.close()

    def poll_prediction(self):
        self.ioloop.run_until_complete(self.prediction_polling_task())


def main():
    basicConfig(level="INFO")
    log_set_level(log_level.debug)
    log_register_sink(print)
    runner = Runner(Args.from_cmdline(__doc__))

    runner.preload_exchanges()
    runner.preload_tokens()
    start_token = runner.graph.lookup_token(START_TOKEN)
    assert start_token
    runner.graph.start_token = start_token
    runner.preload_pools()
    runner.graph.calculate_paths()
    #runner.preload_balances()
    print("LOAD COMPLETE")
    #runner.poll_prediction()
    while True:
        sleep(10)


if __name__ == '__main__':
    main()