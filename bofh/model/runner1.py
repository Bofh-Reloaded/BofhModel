from asyncio import get_event_loop
from concurrent.futures import ThreadPoolExecutor
from os import environ
from os.path import dirname, realpath, join
from random import choice
from threading import Thread, Lock, Event
from time import sleep

from web3.exceptions import ContractLogicError

from bofh.model.modules.delayed_execution import DelayedExecutor
from bofh.model.modules.event_listener import EventLogListenerFactory
from bofh.utils.deploy_contract import deploy_contract
from eth_utils import to_checksum_address
from jsonrpc_base import TransportError
from jsonrpc_websocket import Server

from bofh.utils.misc import progress_printer, LogAdapter, secs_to_human_repr, optimal_cpu_threads
from bofh.utils.solidity import get_abi, add_solidity_search_path, find_contract
from bofh.utils.web3 import Web3Connector, Web3PoolExecutor, JSONRPCConnector, method_id, log_topic_id, \
    parse_data_parameters, bsc_block_age_secs

DEFAULT_MAX_AGE_RESERVES_SNAPSHOT_SECS=3600  # 1hr because probably it would probably take longer to forward the
                                             # existing snapshot rather than downloading from scratch


from dataclasses import dataclass, fields, _MISSING_TYPE, MISSING
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB, StatusScopedCursor, BalancesScopedCursor
from bofh_model_ext import TheGraph, log_level, log_register_sink, log_set_level, PathEvalutionConstraints

# add bofh.contract/contracts to get_abi() seach path:
add_solidity_search_path(join(dirname(dirname(dirname(realpath(__file__)))), "bofh.contract", "contracts"))


PREDICTION_LOG_TOPIC0_SWAP = log_topic_id("Swap(address,uint256,uint256,uint256,uint256,address)")
PREDICTION_LOG_TOPIC0_SYNC = log_topic_id("Sync(uint112,uint112)")
WBNB_address = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c" # id=2
TETHER_address = "0x55d398326f99059ff775485246999027b3197955" # id=4
START_TOKEN = to_checksum_address(WBNB_address)

DEFAULT_SWAP_CONTRACT_ADDRESS = '0x89FD75CBb35267DDA9Bd6d31CdE86607a06dcFAa'
DEFAULT_BOFH_WALLET_ADDRESS = '0xF567a3B93AF6Aa3ef8A084014b2fbc2C17D21A00'
DEFAULT_BOFH_WALLET_PASSWD = 'skajhn398abn.SASA'

ENV_SWAP_CONTRACT_ADDRESS = environ.get("BOFH_CONTRACT_ADDRESS", DEFAULT_SWAP_CONTRACT_ADDRESS)
ENV_BOFH_WALLET_ADDRESS = environ.get("BOFH_WALLET_ADDRESS", DEFAULT_BOFH_WALLET_ADDRESS)
ENV_BOFH_WALLET_PASSWD = environ.get("BOFH_WALLET_PASSWD", DEFAULT_BOFH_WALLET_PASSWD)

@dataclass
class Args:
    status_db_dsn: str = "sqlite3://status.db"
    verbose: bool = False
    web3_rpc_url: str = JSONRPCConnector.connection_uri()
    max_workers: int = optimal_cpu_threads()
    chunk_size: int = 100
    pred_polling_interval: int = 1000
    start_token_address: str = WBNB_address
    max_reserves_snapshot_age_secs: int = 7200
    force_reuse_reserves_snapshot: bool = False
    do_not_update_reserves_from_chain: bool = False
    contract_address: str = DEFAULT_SWAP_CONTRACT_ADDRESS
    wallet_address: str = DEFAULT_BOFH_WALLET_ADDRESS
    wallet_password: str = DEFAULT_BOFH_WALLET_PASSWD
    initial_amount_min: int = 0
    initial_amount_max: int = 10**16
    min_profit_target_ppm: int = 10000
    max_profit_target_ppm: int = None
    min_profit_target_amount: int = 0
    dry_run: bool = False
    dry_run_delay: int = 6
    logfile: str = None
    cli: bool = False

    DB_CACHED_PARAMETERS = {
        # List of parameters which are also stored in DB in a stateful manner
        "web3_rpc_url",
        "start_token_address",
        "pred_polling_interval",
        "max_reserves_snapshot_age_secs",
        "contract_address",
        "wallet_address",
        "wallet_password",
        "initial_amount_min",
        "initial_amount_max",
        "min_profit_target_ppm",
        "max_profit_target_ppm",
        "min_profit_target_amount",
        "dry_run_delay",
    }

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
        kw = {}
        for field in fields(cls):
            k = "--%s" % field.name
            arg = args.get(k)
            if arg is None:
                arg = field.default
                if arg is MISSING:
                    raise RuntimeError("missing command line parameter: %s" % k)
            if arg is not None:
                arg = field.type(arg)
            kw[field.name] = arg
        return cls(**kw)

    def sync_db(self, db):
        self.db = db
        with self.db as curs:
            for fn in self.DB_CACHED_PARAMETERS:
                field = self.__dataclass_fields__[fn]
                curval = super(Args, self).__getattribute__(fn)
                if curval is None:
                    dbval = curs.get_meta(fn, field.default, cast=field.type)
                    super(Args, self).__setattr__(fn, dbval)
                else:
                    curs.set_meta(fn, curval, cast=field.type)

    def __setattr__(self, key, value):
        super(Args, self).__setattr__(key, value)
        if key not in self.DB_CACHED_PARAMETERS:
            return
        db = getattr(self, "db", None)
        if not db:
            return
        with db as curs:
            curs.set_meta(key, value)


__doc__=f"""Start model runner.

Usage: bofh.model.runner1 [options]

Options:
  -h  --help
  -d, --dsn=<connection_str>            DB dsn connection string. Default is {Args.status_db_dsn}
  -c, --web3_rpc_url=<url>              Web3 RPC connection URL. Default is {Args.web3_rpc_url}
  -j, --max_workers=<n>                 number of RPC data ingest workers, default one per hardware thread. Default is {Args.max_workers}
  -v, --verbose                         debug output
  --chunk_size=<n>                      preloaded work chunk size per each worker Default is {Args.chunk_size}
  --pred_polling_interval=<n>           Web3 prediction polling internal in millisecs. Default is {Args.pred_polling_interval}
  --start_token_address=<address>       on-chain address of start token. Default is WBNB_mainnet
  --max_reserves_snapshot_age_secs=<s>  max age of usable LP reserves DB snapshot (refuses to preload from DB if older). Default is {Args.max_reserves_snapshot_age_secs}
  --force_reuse_reserves_snapshot       disregard --max_reserves_snapshot_age_secs (use for debug purposes, avoids download of reserves)       
  --do_not_update_reserves_from_chain   do not attempt to forward an existing reserves DB snapshot to the latest known block
  --contract_address=<address>          set contract counterpart address. Default from BOFH_CONTRACT_ADDRESS envvar
  --wallet_address=<address>            funding wallet address. Default from BOFH_WALLET_ADDRESS envvar
  --wallet_password=<pass>              funding wallet address. Default from BOFH_WALLET_PASSWD envvar
  --initial_amount_min=<wei>            min initial amount of start_token considered for swap operation. Default is {Args.initial_amount_min}
  --initial_amount_max=<wei>            max initial amount of start_token considered for swap operation. Default is {Args.initial_amount_max}
  --min_profit_target_ppm=<ppM>         minimum viable profit target in parts per million (relative). Default is {Args.min_profit_target_ppm}
  --max_profit_target_ppm=<ppM>         minimum viable profit target in parts per million (relative). Default is {Args.max_profit_target_ppm}
  --min_profit_target_amount=<wei>      minimum viable profit target in wei (absolute). Default is unset
  --dry_run                             call contract execution to estimate outcome without actual transaction (no-risk no-reward mode)
  --dry_run_delay=<secs>                delay seconds from opportunity spotting and arbitrage simulation. Default is {Args.dry_run_delay}
  --logfile=<file>                      log to file
  --cli                                 preload status and stop at CLI (for debugging)
"""



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
        self.args.sync_db(self.db)
        self.consistency_checks()
        self.status_lock = Lock()
        self.reserves_update_batch = list()
        self.delayed_executor = DelayedExecutor(self)
        # self.polling_started = Event()

    def consistency_checks(self):
        self.log.info("Runtime parameter map:")
        for f in fields(self.args):
            v = getattr(self.args, f.name)
            if f.name.find("password") > 0:
                v = "*" * len(v)
            self.log.info(" \\____ %s = %s", f.name, v)
        try:
            contract_balance = self.contract_balance()
            self.log.info("contract at %s has %u in balance", self.contract_address, contract_balance)
            if contract_balance < self.args.initial_amount_max or contract_balance < self.args.initial_amount_min:
                self.log.error("financial attack parameters ( --initial_amount_min=%r and --initial_amount_max=%r "
                               ") are not compatible with contract balance"
                               , self.args.initial_amount_min
                               , self.args.initial_amount_max)
        except:
            self.log.error("unable to read current balance for contract at %s", self.contract_address)


    def _get_contract_address(self):
        return self.args.contract_address

    def _set_contract_address(self, addr):
        with self.db as curs:
            curs.set_meta("contract_address", addr)
        self.args.contract_address = addr

    contract_address = property(_get_contract_address, _set_contract_address)

    @property
    def w3(self):
        try:
            return self.__w3
        except AttributeError:
            self.__w3 = Web3Connector.get_connection(self.args.web3_rpc_url)
        return self.__w3

    @property
    def jsonrpc(self):
        try:
            return self.__jsonrpc
        except AttributeError:
            self.__jsonrpc = JSONRPCConnector.get_connection(self.args.web3_rpc_url)
        return self.__jsonrpc

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
                for poolid, reserve0, reserve1 in curs.execute("SELECT id, reserve0, reserve1 FROM pool_reserves").get_all():
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

    def update_balances_from_web3(self, start_block=None):
        per_thread_queue_size = self.args.max_workers * 10
        current_block = self.w3.eth.block_number
        with self.db as curs:
            if start_block is None:
                start_block = curs.reserves_block_number
            latest_read = max(0, start_block-1)
            nr = current_block - latest_read
            if nr <= 0:
                return
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
                            latest_read = next_block
                        executor.shutdown()
                curs.reserves_block_number = latest_read

    def get_constraints(self):
        constraint = PathEvalutionConstraints()
        constraint.initial_token_wei_balance = self.args.initial_amount_min
        constraint.convenience_min_threshold = (self.args.min_profit_target_ppm+1000000) / 1000000
        if not self.args.max_profit_target_ppm:
            constraint.convenience_max_threshold = 10
        else:
            constraint.convenience_max_threshold = (self.args.max_profit_target_ppm+1000000) / 1000000
        return constraint

    def is_out_of_fees_error(self, err):
        return str(err).find("Pancake: K") > 0

    def on_profitable_path_execution(self, match):
        path = match.path
        pools = []
        for i in range(path.size()):
            swap = path.get(i)
            pools.append(str(swap.pool.address))
        feesPPM = [3000] * len(pools)
        initialAmount = self.args.initial_amount_min
        expectedAmount = (initialAmount * (1000000 + self.args.min_profit_target_ppm)) // 1000000
        try:
            payload = self.pack_args_payload(pools, feesPPM, initialAmount, expectedAmount)
            yields = self.call("multiswap", payload)
            self.log.info("SUCCESS: initialAmount=%u %u-way swap yields %u (%d gain, or %0.3f%%)"
                          , initialAmount
                          , len(pools)
                          , yields
                          , yields-initialAmount
                          , (yields/initialAmount)*100.0
                          )
        except:
            self.log.exception("unable to execute dry-run contract estimation")

    async def prediction_polling_task(self, constraint=None):
        # await self.polling_started.wait()
        if constraint is None:
            constraint = self.get_constraints()

        self.log.info("convenience_min_threshold = %r", constraint.convenience_min_threshold)
        self.log.info("convenience_min_threshold = %r", constraint.convenience_min_threshold)
        self.log.info("convenience_max_threshold = %r", constraint.convenience_max_threshold)
        self.log.info("initial_token_wei_balance = %r", constraint.initial_token_wei_balance)

        log_set_level(log_level.info)
        self.latestBlockNumber = 0

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
                with self.status_lock:
                    try:
                        try:
                            self.digest_prediction_payload(result)
                        except:
                            self.log.exception("Error during parsing of eth_consPredictLogs() results")
                        try:
                            matches = self.graph.evaluate_paths_of_interest(constraint)
                            for i, match in enumerate(matches):
                                if constraint.match_limit and i >= constraint.match_limit:
                                    return
                                self.delayed_executor.post(self.on_profitable_path_execution, match)
                                print(len(self.delayed_executor.queue.queue))
                                #self.on_profitable_path_execution(match)
                        except:
                            self.log.exception("Error during execution of TheGraph::evaluate_paths_of_interest()")
                    finally:
                        # forget about predicted states. go back to normal
                        self.graph.clear_lp_of_interest()

                sleep(self.args.pred_polling_interval * 0.001)
        except:
            self.log.exception("Error in prediction polling thread")
        finally:
            self.log.info("prediction polling loop terminated")
            await server.close()

    def search_opportunities_by_prediction_thread(self, constraint=None):
        self._search_opportunities_by_prediction_thread = Thread(target=lambda: self.ioloop.run_until_complete(self.prediction_polling_task(constraint)), daemon=True)
        self._search_opportunities_by_prediction_thread.start()

    def update_pool_reserves_by_tx_sync_log(self, pool, r0, r1):
        if self.args.verbose:
            self.log.info("use Sync event to update reserves of pool %r: %s(%s-%s), reserve=%r, reserve1=%r"
                          , pool.address
                          , pool.exchange.name
                          , pool.token0.symbol
                          , pool.token1.symbol
                          , r0
                          , r1)
        pool.setReserves(r0, r1)

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
                try:
                    r0, r1 = parse_data_parameters(log["data"])
                    self.update_pool_reserves_by_tx_sync_log(pool, r0, r1)
                    self.graph.add_lp_of_interest(pool)
                except:
                    continue
                continue
            """
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
            """

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

    def track_swaps_thread(self):
        if getattr(self, "_track_swaps_thread", None):
            self.log.error("track_swaps_thread already started")
        self._track_swaps_thread = Thread(target=self._track_swaps_task, daemon=True)
        self._track_swaps_thread.start()

    def _track_swaps_task(self):
        try:
            factory = EventLogListenerFactory(self, self.args.web3_rpc_url)
            factory.run()
        finally:
            del self._track_swaps_thread

    def periodic_reserve_flush_thread(self):
        if getattr(self, "_periodic_reserve_flush_thread", None):
            self.log.error("periodic_reserve_flush_thread already started")
        self._periodic_reserve_flush_thread = Thread(target=self._periodic_reserve_flush_task, daemon=True)
        self._periodic_reserve_flush_thread.start()

    def _periodic_reserve_flush_task(self):
        self._periodic_reserve_flush_terminated = Event()
        while True:
            if self._periodic_reserve_flush_terminated.wait(timeout=60):
                return
            if not self.reserves_update_batch:
                continue
            if self.args.verbose:
                self.log.info("syncing %u pool reserves udates to db...", len(self.reserves_update_batch))
            with self.status_lock, self.db as curs:
                for pid, r0, r1 in self.reserves_update_batch:
                    curs.add_pool_reserve(pid, r0, r1)
                self.reserves_update_batch.clear()

    def join(self):
        th = getattr(self, "_search_opportunities_by_prediction_thread", None)
        if th:
            th.join()
        th = getattr(self, "_track_swaps_thread", None)
        if th:
            th.join()
        th = getattr(self, "_periodic_reserve_flush_thread", None)
        if th:
            th.join()

    def on_sync_event(self, address, reserve0, reserve1):
        with self.status_lock:
            pool = self.graph.lookup_lp(address)
            if pool:
                self.update_pool_reserves_by_tx_sync_log(pool, reserve0, reserve1)
                self.reserves_update_batch.append((pool.tag, reserve0, reserve1))

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

    def call(self, name, *args, address=None, abi=None):
        if address is None:
            address = self.contract_address
        address = to_checksum_address(address)
        if abi is None:
            abi = "BofhContract"
        contract_instance = self.w3.eth.contract(address=address, abi=get_abi(abi))
        callable = getattr(contract_instance.functions, name)
        return callable(*args).call({"from": self.args.wallet_address})

    def transact(self, name, *args, address=None, abi=None):
        if address is None:
            address = self.contract_address
        address = to_checksum_address(address)
        if abi is None:
            abi = "BofhContract"
        contract_instance = self.w3.eth.contract(address=address, abi=get_abi(abi))
        self.w3.geth.personal.unlock_account(self.args.wallet_address, self.args.wallet_password, 120)
        callable = getattr(contract_instance.functions, name)
        return callable(*args).transact({"from": self.args.wallet_address})

    def add_funding(self, amount):
        caddr = self.contract_address
        self.log.info("approving %u of balance to on contract at %s, then calling adoptAllowance()", amount, caddr)
        self.transact("approve", caddr, amount, address=self.args.start_token_address, abi="IGenericFungibleToken")
        self.transact("adoptAllowance")

    def repossess_funding(self):
        caddr = self.contract_address
        self.log.info("calling withdrawFunds() on contract at %s", caddr)
        self.transact("approve", caddr, 0, address=self.args.start_token_address, abi="IGenericFungibleToken")
        self.transact("withdrawFunds")

    def kill_contract(self):
        caddr = self.contract_address
        self.transact("approve", caddr, 0, address=self.args.start_token_address, abi="IGenericFungibleToken")
        self.log.info("calling kill() on contract at %s", caddr)
        self.transact("kill")

    def contract_balance(self):
        caddr = self.contract_address
        return self.call("balanceOf", caddr, address=self.args.start_token_address, abi="IGenericFungibleToken")

    def redeploy_contract(self, fpath="BofhContract.sol"):
        try:
            self.kill_contract()
        except ContractLogicError:
            self.log.exception("unable to kill existing contract at %s", self.contract_address)
        fpath = find_contract(fpath)
        self.log.info("attempting to deploy contract from %s", fpath)
        self.contract_address = deploy_contract(self.args.wallet_address, self.args.wallet_password, fpath,
                                                self.args.start_token_address)
        self.log.info("new contract address is established at %s", self.contract_address)

    def chiama_multiswap1(self):
        #self.transact("withdrawFunds", "0x9aa063A00809D21388f8f9Dcc415Be866aCDCC0a", "BofhContract")
        return self.call("multiswap1", self.test_payload)

    @staticmethod
    def pack_args_payload(pools: list, fees: list, initialAmount: int, expectedAmount: int):
        assert len(pools) == len(fees)
        assert len(pools) <= 4
        args = []
        for addr, fee in zip(pools, fees):
            args.append(int(str(addr), 16) | (fee << 160))
        amounts_word = \
            ((initialAmount & 0xffffffffffffffffffffffffffffffff) << 0) | \
            ((expectedAmount & 0xffffffffffffffffffffffffffffffff) << 128)
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
        initialAmount = 10**15 # 0.001 WBNB
        expectedAmount = 0 #10**15+1
        return self.pack_args_payload(pools, feePPM, initialAmount, expectedAmount)

    def call_test(self, name, *a, caddr=None):
        if caddr is None:
            caddr = self.contract_address
        args = self.test_payload
        print(self.call(name, caddr, "BofhContract", args, *a))


def main():
    from IPython import embed
    args = Args.from_cmdline(__doc__)
    if args.logfile:
        basicConfig(
            filename=args.logfile,
            filemode="a",
            format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
            level="INFO",
        )
    else:
        import coloredlogs
        coloredlogs.install()
    log_set_level(log_level.debug)
    log_register_sink(LogAdapter(level="DEBUG"))

    bofh = Runner(args)
    bofh.load()
    bofh.track_swaps_thread()
    bofh.periodic_reserve_flush_thread()
    bofh.search_opportunities_by_prediction_thread()
    if args.cli:
        while True:
            embed()
    else:
        bofh.join()


if __name__ == '__main__':
    main()
