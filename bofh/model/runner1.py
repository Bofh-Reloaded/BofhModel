from asyncio import get_event_loop
from functools import lru_cache
from os.path import dirname, realpath, join
from threading import Thread, Lock, Event

from web3.exceptions import ContractLogicError

from bofh.model.modules.constant_prediction import ConstantPrediction
from bofh.model.modules.constants import START_TOKEN, ENV_SWAP_CONTRACT_ADDRESS, ENV_BOFH_WALLET_ADDRESS, \
    ENV_BOFH_WALLET_PASSWD, PREDICTION_LOG_TOPIC0_SYNC
from bofh.model.modules.delayed_execution import DelayedExecutor
from bofh.model.modules.event_listener import EventLogListenerFactory
from bofh.model.modules.status_preloaders import EntitiesPreloader
from bofh.utils.deploy_contract import deploy_contract
from eth_utils import to_checksum_address

from bofh.utils.misc import LogAdapter, optimal_cpu_threads
from bofh.utils.solidity import get_abi, add_solidity_search_path, find_contract
from bofh.utils.web3 import Web3Connector, JSONRPCConnector, parse_data_parameters, bsc_block_age_secs

DEFAULT_MAX_AGE_RESERVES_SNAPSHOT_SECS=3600  # 1hr because probably it would probably take longer to forward the
                                             # existing snapshot rather than downloading from scratch


from dataclasses import dataclass, fields, MISSING
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB, StatusScopedCursor, BalancesScopedCursor, Intervention
from bofh_model_ext import TheGraph, log_level, log_register_sink, log_set_level, PathEvalutionConstraints

# add bofh.contract/contracts to get_abi() seach path:
add_solidity_search_path(join(dirname(dirname(dirname(realpath(__file__)))), "bofh.contract", "contracts"))



@dataclass
class Args:
    status_db_dsn: str = "sqlite3://status.db"
    verbose: bool = False
    web3_rpc_url: str = JSONRPCConnector.connection_uri()
    max_workers: int = optimal_cpu_threads()
    chunk_size: int = 100
    pred_polling_interval: int = 1000
    start_token_address: str = START_TOKEN
    max_reserves_snapshot_age_secs: int = 7200
    force_reuse_reserves_snapshot: bool = False
    do_not_update_reserves_from_chain: bool = False
    contract_address: str = ENV_SWAP_CONTRACT_ADDRESS
    wallet_address: str = ENV_BOFH_WALLET_ADDRESS
    wallet_password: str = ENV_BOFH_WALLET_PASSWD
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


class Runner(EntitiesPreloader, ConstantPrediction):
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
            self.log.info("contract at %s has %u in balance", self.args.contract_address, contract_balance)
            if contract_balance < self.args.initial_amount_max or contract_balance < self.args.initial_amount_min:
                self.log.error("financial attack parameters ( --initial_amount_min=%r and --initial_amount_max=%r "
                               ") are not compatible with contract balance"
                               , self.args.initial_amount_min
                               , self.args.initial_amount_max)
        except:
            self.log.error("unable to read current balance for contract at %s", self.args.contract_address)



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

    def get_constraints(self):
        constraint = PathEvalutionConstraints()
        constraint.initial_token_wei_balance = self.args.initial_amount_min
        constraint.convenience_min_threshold = (self.args.min_profit_target_ppm+1000000) / 1000000
        if not self.args.max_profit_target_ppm:
            constraint.convenience_max_threshold = 10
        else:
            constraint.convenience_max_threshold = (self.args.max_profit_target_ppm+1000000) / 1000000
        return constraint

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

    @lru_cache
    def get_contract(self, address=None, abi=None):
        if address is None:
            address = self.args.contract_address
        if abi is None:
            abi = "BofhContract"
        return self.w3.eth.contract(address=address, abi=get_abi(abi))

    def call(self, name, *args, address=None, abi=None):
        contract_instance = self.get_contract(address=address, abi=abi)
        callable = getattr(contract_instance.functions, name)
        return callable(*args).call({"from": self.args.wallet_address})

    def transact(self, name, *args, address=None, abi=None):
        contract_instance = self.get_contract(address=address, abi=abi)
        self.w3.geth.personal.unlock_account(self.args.wallet_address, self.args.wallet_password, 120)
        callable = getattr(contract_instance.functions, name)
        return callable(*args).transact({"from": self.args.wallet_address})

    def add_funding(self, amount):
        caddr = self.args.contract_address
        self.log.info("approving %u of balance to on contract at %s, then calling adoptAllowance()", amount, caddr)
        self.transact("approve", caddr, amount, address=self.args.start_token_address, abi="IGenericFungibleToken")
        self.transact("adoptAllowance")

    def repossess_funding(self):
        caddr = self.args.contract_address
        self.log.info("calling withdrawFunds() on contract at %s", caddr)
        self.transact("approve", caddr, 0, address=self.args.start_token_address, abi="IGenericFungibleToken")
        self.transact("withdrawFunds")

    def kill_contract(self):
        caddr = self.args.contract_address
        self.transact("approve", caddr, 0, address=self.args.start_token_address, abi="IGenericFungibleToken")
        self.log.info("calling kill() on contract at %s", caddr)
        self.transact("kill")

    def contract_balance(self):
        caddr = self.args.contract_address
        return self.call("balanceOf", caddr, address=self.args.start_token_address, abi="IGenericFungibleToken")

    def redeploy_contract(self, fpath="BofhContract.sol"):
        try:
            self.kill_contract()
        except ContractLogicError:
            self.log.exception("unable to kill existing contract at %s", self.args.contract_address)
        fpath = find_contract(fpath)
        self.log.info("attempting to deploy contract from %s", fpath)
        self.args.contract_address = deploy_contract(self.args.wallet_address, self.args.wallet_password, fpath,
                                                self.args.start_token_address)
        self.log.info("new contract address is established at %s", self.args.contract_address)

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
            caddr = self.args.contract_address
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
