from asyncio import get_event_loop
from concurrent.futures import ThreadPoolExecutor
from os.path import dirname, realpath, join
from random import choice
from time import sleep

from eth_utils import to_checksum_address
from jsonrpc_base import TransportError
from jsonrpc_websocket import Server

from bofh.utils.misc import progress_printer, LogAdapter, secs_to_human_repr, optimal_cpu_threads
from bofh.utils.solidity import get_abi, add_solidity_search_path
from bofh.utils.web3 import Web3Connector, Web3PoolExecutor, JSONRPCConnector, method_id, log_topic_id, \
    parse_data_parameters, bsc_block_age_secs

DEFAULT_MAX_AGE_RESERVES_SNAPSHOT_SECS=3600  # 1hr because probably it would probably take longer to forward the
                                             # existing snapshot rather than downloading from scratch

__doc__="""Start model runner.

Usage: bofh.model.runner1 [options]

Options:
  -h  --help
  -d, --dsn=<connection_str>            DB dsn connection string [default: sqlite3://status.db]
  -c, --connection_url=<url>            Web3 RPC connection URL [default: LOCAL_WS_RPC]
  -n <n>                                number of pools to query before exit (benchmark mode)
  -j <n>                                number of RPC data ingest workers, default one per hardware thread [default: %u]
  -v, --verbose                         debug output
  --chunk_size=<n>                      preloaded work chunk size per each worker [default: 100]
  --pred_polling_interval=<n>           Web3 prediction polling internal in millisecs [default: 1000]
  --start_token_address=<address>       on-chain address of start token [default: WBNB]
  --max_reserves_snapshot_age_secs=<s>  max age of usable LP reserves DB snapshot (refuses to preload from DB if older) [default: %r]
  --force_reuse_reserves_snapshot       disregard --max_reserves_snapshot_age_secs (use for debug purposes, avoids download of reserves)       
  --do_not_update_reserves_from_chain    do not attempt to forward an existing reserves DB snapshot to the latest known block       
  --cli                                 preload status and stop at CLI (for debugging)
""" % (optimal_cpu_threads(), DEFAULT_MAX_AGE_RESERVES_SNAPSHOT_SECS)

from dataclasses import dataclass
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB, StatusScopedCursor, BalancesScopedCursor
from bofh_model_ext import TheGraph, log_level, log_register_sink, log_set_level, PathEvalutionConstraints

# add bofh.contract/contracts to get_abi() seach path:
add_solidity_search_path(join(dirname(dirname(dirname(realpath(__file__)))), "bofh.contract", "contracts"))


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
    start_token_address: str = None
    max_reserves_snapshot_age_secs: int = 0
    force_reuse_reserves_snapshot: bool = False
    do_not_update_reserves_from_chain: bool = False
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
            , web3_rpc_url=cls.default(args["--connection_url"], "", suppress_list=["LOCAL_WS_RPC"])
            , max_workers=int(cls.default(args["-j"], 0))
            , chunk_size=int(cls.default(args["--chunk_size"], 100))
            , pred_polling_interval=int(cls.default(args["--pred_polling_interval"], 1000))
            , start_token_address=cls.default(args["--start_token_address"], "", suppress_list=["WBNB"])
            , max_reserves_snapshot_age_secs=int(args["--max_reserves_snapshot_age_secs"])
            , force_reuse_reserves_snapshot=bool(cls.default(args["--force_reuse_reserves_snapshot"], 0))
            , do_not_update_reserves_from_chain=bool(cls.default(args["--do_not_update_reserves_from_chain"], 0))
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
        self.pools = set()
        self.ioloop = get_event_loop()
        self.align_settings_in_db()
        # self.polling_started = Event()

    def align_settings_in_db(self):
        with self.db as curs:
            if not self.args.start_token_address or self.args.start_token_address == START_TOKEN:
                self.args.start_token_address = curs.get_meta("start_token_address", START_TOKEN)
            curs.set_meta("start_token_address", self.args.start_token_address)
            if not self.args.web3_rpc_url:
                self.args.web3_rpc_url = curs.get_meta("web3_rpc_url", Web3Connector.DEFAULT_URI_WSRPC)
            curs.set_meta("web3_rpc_url", self.args.web3_rpc_url)
            if not self.args.pred_polling_interval or self.args.pred_polling_interval == 1000:
                self.args.pred_polling_interval = curs.get_meta("pred_polling_interval", 1000, cast=int)
            curs.set_meta("pred_polling_interval", self.args.pred_polling_interval)
            if not self.args.max_reserves_snapshot_age_secs or self.args.max_reserves_snapshot_age_secs == DEFAULT_MAX_AGE_RESERVES_SNAPSHOT_SECS:
                self.args.max_reserves_snapshot_age_secs = curs.get_meta("max_reserves_snapshot_age_secs", DEFAULT_MAX_AGE_RESERVES_SNAPSHOT_SECS, cast=int)
            curs.set_meta("max_reserves_snapshot_age_secs", self.args.max_reserves_snapshot_age_secs)

    @property
    def w3(self):
        try:
            return self.__w3
        except AttributeError:
            self.__w3 = Web3Connector.get_connection(self.args.web3_rpc_url)
        return self.__w3


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
                    print_progress()
                    #t0 = self.graph.lookup_token(token0_id)
                    #t1 = self.graph.lookup_token(token1_id)
                    #if not t0 or not t1:
                    #    if self.args.verbose:
                    #        self.log.warning("disabling pool %s due to missing or disabled affering token "
                    #                         "(token0=%r, token1=%r)", address, token0_id, token1_id)
                    #    continue
                    #exchange = self.graph.lookup_exchange(exchange_id)
                    #assert exchange is not None
                    #pool = self.graph.add_lp(id, address, exchange, t0, t1)
                    pool = self.graph.add_lp(id, address, exchange_id, token0_id, token1_id)
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
        if not self.preload_balances_from_db():
            self.download_reserves_snapshot_from_web3()
        if not self.args.do_not_update_reserves_from_chain:
            self.update_balances_from_web3()

    def download_reserves_snapshot_from_web3(self):
        self.log.info("downloading a new reserves snapshot from Web3")
        print_progress = progress_printer(self.pools_ctr
                                          , "fetching pool reserves {percent}% ({count} of {tot}"
                                            " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                          , on_same_line=True)
        with Web3PoolExecutor(connection_uri=self.args.web3_rpc_url, max_workers=self.args.max_workers) as executor:
            self.log.info("concurrent reserves download via Web3:"
                     "\n\t- %r pool getReserve requests"
                     "\n\t- on Web3 servant at %s"
                     "\n\t- using %d workers"
                     "\n\t- each with a %d preload queue"
                      , self.pools_ctr
                      , self.args.web3_rpc_url
                      , self.args.max_workers
                      , self.args.chunk_size
                      )
            with self.db as curs:
                try:
                    currentBlockNr = self.w3.eth.block_number
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
                            pool = self.graph.lookup_lp(pool_addr)
                            assert pool
                            curs.add_pool_reserve(pool.tag, reserve0, reserve1)
                            print_progress()
                        except:
                            self.log.exception("unable to query pool %s", pool_addr)
                        curs.reserves_block_number = currentBlockNr
                finally:
                    curs.reserves_block_number = currentBlockNr
            executor.shutdown(wait=True)

    def preload_balances_from_db(self):
        with self.db as curs:
            latest_blocknr = curs.reserves_block_number
            current_blocknr = self.w3.eth.block_number
            age = current_blocknr-latest_blocknr
            if not latest_blocknr or age < 0:
                self.log.warning("unable to preload reserves from DB (latest block number not set in DB, or invalid)")
                return
            age_secs = bsc_block_age_secs(age)
            self.log.info("reserves DB snapshot is for block %u (%d blocks old), which is %s old"
                          , latest_blocknr
                          , age
                          , secs_to_human_repr(age_secs))
            if not self.args.force_reuse_reserves_snapshot:
                if age_secs > self.args.max_reserves_snapshot_age_secs:
                    self.log.warning("reserves DB snapshot is too old (older than --max_reserves_snapshot_age_secs=%r)"
                                     , self.args.max_reserves_snapshot_age_secs)
                    return
            else:
                self.log.warning(
                    "forcing reuse of existing reserves DB snapshot (as per --force_reuse_reserves_snapshot)")

            self.log.info("fetching LP reserves previously saved in db")
            nr = curs.execute("SELECT COUNT(1) FROM pool_reserves").get_int()
            with progress_printer(nr, "fetching pool reserves {percent}% ({count} of {tot}"
                                       " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                       , on_same_line=True) as print_progress:

                ok = 0
                disc = 0
                for poolid, reserve0, reserve1 in curs.execute("SELECT id, reserve0, reserve1 FROM reserves").get_all():
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
            return True

    def reserves_parse_blocknr(self, blocknr):
        block = self.w3.eth.get_block(blocknr)
        if not block:
            return
        txs = block.get("transactions")
        if not txs:
            return

        with self.db as curs:
            try:
                for txh in txs:
                    txr = self.w3.eth.get_transaction_receipt(txh)
                    if not txr:
                        continue
                    logs = txr.get("logs")
                    if not logs:
                        continue
                    for log in logs:
                        topics = log.get("topics")
                        address = log.get("address")
                        if address and topics and topics[0] == PREDICTION_LOG_TOPIC0_SYNC:
                            pool = self.graph.lookup_lp(address)
                            if not pool:
                                continue
                            self.update_pool_reserves_by_tx_sync_log(pool, log["data"], curs)
            except:
                self.db.rollback()
                raise

    def update_balances_from_web3(self):
        per_thread_queue_size = self.args.max_workers * 10
        current_block = self.w3.eth.block_number
        with self.db as curs:
            latest_read = curs.reserves_block_number
            nr = current_block - latest_read
            with progress_printer(nr, "rolling forward pool reserves {percent}% ({count} of {tot}"
                                      " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                      , on_same_line=True) as print_progress:
                while True:
                    nr = current_block - latest_read
                    print_progress.tot = nr
                    if nr <= 0:
                        self.log.info("LP balances updated to current block (%u)", current_block)
                        break
                    target = min(latest_read+per_thread_queue_size, current_block+1)
                    with ThreadPoolExecutor(max_workers=self.args.max_workers) as executor:
                        for next_block in range(latest_read, target):
                            self.log.debug("loading reserves from block %r ... ", next_block)
                            if print_progress():
                                self.db.commit()
                            executor.submit(self.reserves_parse_blocknr, next_block)
                            curs.reserves_block_number = latest_read = next_block
                        executor.shutdown()

    def get_constraints(self):
        constraint = PathEvalutionConstraints()
        constraint.initial_token_wei_balance = self.graph.start_token.toWei(1)
        return constraint

    async def prediction_polling_task(self, constraint=None):
        # await self.polling_started.wait()
        if constraint is None:
            constraint = self.get_constraints()
        log_set_level(log_level.info)
        self.latestBlockNumber = 0
        res = []

        self.log.info("entering prediction polling loop...")
        server = Server(self.args.web3_rpc_url)
        try:
            await server.ws_connect()
            while True:  # self.polling_started.is_set():
                try:
                    result = await server.eth_consPredictLogs(0, 0, PREDICTION_LOG_TOPIC0_SYNC, PREDICTION_LOG_TOPIC0_SWAP)
                    blockNumber = result["blockNumber"]
                    if blockNumber <= self.latestBlockNumber:
                        continue
                    self.log.info("prediction results are in for block %r", blockNumber)
                    self.latestBlockNumber = blockNumber
                except TransportError:
                    # server disconnected
                    raise
                except:
                    self.log.exception("Error during eth_consPredictLogs() RPC execution")
                    continue
                try:
                    try:
                        self.digest_prediction_payload(result)
                    except:
                        self.log.exception("Error during parsing of eth_consPredictLogs() results")
                    try:
                        matches = self.graph.evaluate_paths_of_interest(constraint)
                        if constraint.match_limit:
                            for m in matches:
                                res.append(m)
                                if len(res) >= constraint.match_limit:
                                    return res
                    except:
                        self.log.exception("Error during execution of TheGraph::evaluate_paths_of_interest()")
                    finally:
                        self.graph.clear_lp_of_interest()
                finally:
                    # forget about predicted states. go back to normal
                    self.graph.clear_lp_of_interest()

                sleep(self.args.pred_polling_interval * 0.001)
        except:
            self.log.exception("Error in prediction polling thread")
        finally:
            self.log.info("prediction polling loop terminated")
            await server.close()

    def search_opportunities_by_prediction(self, constraint=None):
        return self.ioloop.run_until_complete(self.prediction_polling_task(constraint))

    def update_pool_reserves_by_tx_sync_log(self, pool, data, curs=None):
        try:
            r0, r1 = parse_data_parameters(data)
        except:
            self.log.exception("unable to decode sync log data")
            return
        if self.args.verbose:
            self.log.info("use Sync event to update reserves of pool %r: %s(%s-%s), reserve=%r, reserve1=%r"
                          , pool.address
                          , pool.exchange.name
                          , pool.token0.symbol
                          , pool.token1.symbol
                          , r0
                          , r1)
        pool.setReserves(r0, r1)
        if curs:
            curs.add_pool_reserve(pool.tag, r0, r1)

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
                pool.enter_predicted_state(0, 0, 0, 0)
                self.update_pool_reserves_by_tx_sync_log(pool, log["data"])
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

    def load(self):
        self.preload_exchanges()
        self.preload_tokens()
        start_token = self.graph.lookup_token(self.args.start_token_address)
        if not start_token:
            msg = "start_token not found: address %s is unknown or not of a token" % self.args.start_token_address
            self.log.error(msg)
            raise RuntimeError(msg)
        else:
            self.log.info("start_token is %s (%s)", start_token.symbol, start_token.address)
            self.graph.start_token = start_token
        self.preload_pools()
        self.graph.calculate_paths()
        self.preload_balances()
        self.log.info("  *********************************")
        self.log.info("  ***  GRAPH LOAD COMPLETE :-)  ***")
        self.log.info("  *********************************")


    def costruisci_invocabile_da_path(self, path):
        wbnb_amount = 0.1
        min_profit_pct = 1
        address_vector = [str(self.graph.start_token.address)]
        for i in range(path.size()):
            swap = path.get(i)
            address_vector.append(str(swap.tokenDest.address))
        self.log.info("address vector is %r", address_vector)
        initial_amount = int(str(self.graph.start_token.toWei(wbnb_amount)))
        return self.costruisci_invocabile_da_parametri(address_vector, initial_amount, min_profit_pct)

    SWAP_CONTRACT_ADDRESS = '0xF11e70E0Af6D0a032147369A85E2aDBA881FB727'
    SWAP_CONTRACT_ADDRESS = '0x6320C0C8057b46a1660CaDBC482f34637b30f342'
    SWAP_CONTRACT_ADDRESS = '0xc7f824D3Dd28493e9fa4aAE1545D256997Bc4DBE'
    SWAP_CONTRACT_ADDRESS = '0x21E433bA868B94A22128A8E2208BAD49AD73eD84'
    SWAP_CONTRACT_ADDRESS = '0x86EeD7B9B398380d113163D0505115Da6BFaE6c2'
    SWAP_CONTRACT_ADDRESS = '0x30151bff48c445D0451b87eDADaf21BA16cBF00E'
    SWAP_CONTRACT_ADDRESS = '0x89FD75CBb35267DDA9Bd6d31CdE86607a06dcFAa'


    TOKEN_ADDR = "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd"
    ACCOUNT_CREDS = '0xF567a3B93AF6Aa3ef8A084014b2fbc2C17D21A00', "skajhn398abn.SASA" # pkey, password

    def call(self, name, address, abi, *args):
        address = to_checksum_address(address)
        contract_instance = self.w3.eth.contract(address=address, abi=get_abi(abi))
        callable = getattr(contract_instance.functions, name)
        return callable(*args).call({"from": self.ACCOUNT_CREDS[0]})

    def transact(self, name, address, abi, *args):
        address = to_checksum_address(address)
        contract_instance = self.w3.eth.contract(address=address, abi=get_abi(abi))
        self.w3.geth.personal.unlock_account(*self.ACCOUNT_CREDS, 120)
        callable = getattr(contract_instance.functions, name)
        return callable(*args).transact({"from": self.ACCOUNT_CREDS[0]})

    def aggiungi_fondi(self, amount, caddr=None):
        if caddr is None:
            caddr = self.SWAP_CONTRACT_ADDRESS
        self.transact("approve", self.TOKEN_ADDR, "IGenericFungibleToken", caddr, amount)
        self.transact("adoptAllowance", caddr, "BofhContract")

    def preleva_fondi(self, caddr=None):
        if caddr is None:
            caddr = self.SWAP_CONTRACT_ADDRESS
        self.transact("withdrawFunds", caddr, "BofhContract")

    def kill_contract(self, caddr=None):
        if caddr is None:
            caddr = self.SWAP_CONTRACT_ADDRESS
        self.transact("kill", caddr, "BofhContract")

    def contract_balance(self, caddr=None):
        if caddr is None:
            caddr = self.SWAP_CONTRACT_ADDRESS
        return self.call("balanceOf", self.TOKEN_ADDR, "IGenericFungibleToken", caddr)





    def chiama_multiswap1(self, caddr=None):
        if caddr is None:
            caddr = self.SWAP_CONTRACT_ADDRESS
        args = self.test_payload
        #self.transact("withdrawFunds", "0x9aa063A00809D21388f8f9Dcc415Be866aCDCC0a", "BofhContract")
        print(self.call("multiswap1", caddr, "BofhContract", args))

    @staticmethod
    def pack_args_payload(pools: list, fees: list, initialAmount: int, expectedAmount: int):
        assert len(pools) == len(fees)
        assert len(pools) <= 4
        args = []
        fee_word = 0
        shl = 0
        for feePPM in fees:
            fee_word |= ((feePPM & 0xffffffff) << shl)
            shl += 32
        amounts_word = \
            ((initialAmount & 0xffffffffffffffffffffffffffffffff) << 0) | \
            ((expectedAmount & 0xffffffffffffffffffffffffffffffff) << 128)
        for addr in pools:
            args.append(int(str(addr), 16))
        args.append(fee_word)
        args.append(amounts_word)
        return args

    @property
    def test_payload(self):
        pools = [
            "0xf7735324b1ad67b34d5958ed2769cffa98a62dff", # WBNB <-> USDT
            "0xaf9399f70d896da0d56a4b2cbf95f4e90a6b99e8", # USDT <-> DAI
            "0xc64c507d4ba4cab02840cecd5878cb7219e81fe0", # DAI <-> WBNB
        ]
        feePPM = [20000+i for i in range(len(pools))]
        initialAmount = 10**16 # 0.01 WBNB
        expectedAmount = 10**16+1
        return self.pack_args_payload(pools, feePPM, initialAmount, expectedAmount)

    def call_test(self, name, *a, caddr=None):
        if caddr is None:
            caddr = self.SWAP_CONTRACT_ADDRESS
        args = self.test_payload
        print(self.call(name, caddr, "BofhContract", args, *a))




"""
    def chiamaIlCoso(self, tokens, constraint):
        import web3
        to_checksum_address()
address = '0xE2C2b4DDA45bb4B70D718954148a181d760D515A'
contracts = [{'inputs': [{'internalType': 'address[]',
        'name': 'tokenPath',
        'type': 'address[]'},
       {'internalType': 'address', 'name': 'startToken', 'type': 'address'},
       {'internalType': 'uint256', 'name': 'initialAmount', 'type': 'uint256'},
       {'internalType': 'uint256', 'name': 'minProfit', 'type': 'uint256'}],
      'name': 'doCakeInternalSwaps',
      'outputs': [],
      'stateMutability': 'nonpayable',
      'type': 'function'}]
def path_to_token_array():
    res = [str(self.graph.start_token.address)]
    for i in range(path.size()):
        swap = path.get(i)
        res.append(str(swap.tokenDest.address))
    return res
initial_amount = int(str(constraint.initial_token_wei_balance))
min_profit = int(initial_amount * 0.01)
w3 = Web3Connector.get_connection(self.args.web3_rpc_url)
contract_instance = w3.eth.contract(address=address, contracts=contracts)
tx_hash = contract_instance.functions.doCakeInternalSwaps(
    tokens
    , str(self.graph.start_token.address)
    , initial_amount
    , min_profit
).transact()
self.log.info("SWAP contract invocation: %s", tx_hash)
"""

def main():
    basicConfig(level="INFO")
    log_set_level(log_level.debug)
    log_register_sink(LogAdapter(level="DEBUG"))
    args = Args.from_cmdline(__doc__)
    runner = Runner(args)
    if args.cli:
        from IPython import embed
        embed()
    else:
        runner.load()
        runner.search_opportunities_by_prediction()
"""
tokens = ["0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "0xbB8203e945866A1f3Eced6e5B22679E5A540be91", "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82", "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"]
constraint = PathEvalutionConstraints()
constraint.initial_token_wei_balance = int(int(str(runner.graph.start_token.toWei(1))) / 10)

runner.chiamaIlCoso(tokens, constraint) 
INFO:bofh_model:candidate path Polkadot(0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c-0xbb8203e945866a1f3eced6e5b22679e5a540be91, 493597), 
Polkadot(0xbb8203e945866a1f3eced6e5b22679e5a540be91-0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82, 494733), 
Polkadot(0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82-0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c, 11) would yield 3.61716%
"""


if __name__ == '__main__':
    main()