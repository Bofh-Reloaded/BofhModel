from asyncio import get_event_loop
from os.path import dirname, realpath, join
from threading import Lock
from time import time

from coloredlogs import ColoredFormatter
from eth_utils import to_checksum_address
from web3.exceptions import ContractLogicError

from bofh.model.modules.graph import TheGraph
from bofh.model.modules.constant_prediction import ConstantPrediction
from bofh.model.modules.delayed_execution import DelayedExecutor
from bofh.model.modules.event_listener import SyncEventRealtimeTracker
from bofh.model.modules.loggers import Loggers
from bofh.model.modules.status_preloaders import EntitiesPreloader
from bofh.model.modules.contract_calls import ContractCalling

from bofh.utils.solidity import add_solidity_search_path

from dataclasses import dataclass, fields, MISSING
from logging import basicConfig, Filter, getLogger

from bofh.model.database import ModelDB, StatusScopedCursor, Attack
from bofh_model_ext import log_level, log_register_sink, log_set_level, PathEvalutionConstraints

# add bofh.contract/contracts to get_abi() seach path:
from bofh.utils.config_data import BOFH_START_TOKEN_ADDRESS, BOFH_CONTRACT_ADDRESS, BOFH_WALLET_ADDRESS, \
    BOFH_WALLET_PASSWD, BOFH_STATUS_DB_DSN, BOFH_REPORTS_DB_DSN, BOFH_ATTACKS_DB_DSN, BOFH_WEB3_RPC_URL, \
    BOFH_MAX_WORKERS, BOFH_ATTACK_INITIAL_AMOUNT_MIN, BOFH_ATTACK_INITIAL_AMOUNT_MAX, BOFH_ATTACK_MIN_PROFIT_PPM, \
    BOFH_ATTACK_MAX_PROFIT_PPM, BOFH_ATTACK_MIN_PROFIT_AMOUNT

add_solidity_search_path(join(dirname(dirname(dirname(realpath(__file__)))), "bofh.contract", "contracts"))


@dataclass
class Args:
    status_db_dsn: str = BOFH_STATUS_DB_DSN
    reports_db_dsn: str = BOFH_REPORTS_DB_DSN
    attacks_db_dsn: str = BOFH_ATTACKS_DB_DSN
    verbose: bool = False
    web3_rpc_url: str = BOFH_WEB3_RPC_URL
    max_workers: int = BOFH_MAX_WORKERS
    chunk_size: int = 100
    pred_polling_interval: int = 1000
    start_token_address: str = BOFH_START_TOKEN_ADDRESS
    max_reserves_snapshot_age_secs: int = 7200
    force_reuse_reserves_snapshot: bool = False
    do_not_update_reserves_from_chain: bool = False
    contract_address: str = BOFH_CONTRACT_ADDRESS
    wallet_address: str = BOFH_WALLET_ADDRESS
    wallet_password: str = BOFH_WALLET_PASSWD
    initial_amount_min: int = BOFH_ATTACK_INITIAL_AMOUNT_MIN
    initial_amount_max: int = BOFH_ATTACK_INITIAL_AMOUNT_MAX
    path_estimation_amount: int = 10**16
    min_profit_target_ppm: int = BOFH_ATTACK_MIN_PROFIT_PPM
    max_profit_target_ppm: int = BOFH_ATTACK_MAX_PROFIT_PPM
    min_profit_target_amount: int = BOFH_ATTACK_MIN_PROFIT_AMOUNT
    attacks_mute_cache_size: int = 0
    attacks_mute_cache_deadline: int = 3600
    dry_run: bool = False
    dry_run_delay: int = 6
    logfile: str = None
    cli: bool = False
    loglevel_runner: str = "INFO"
    loglevel_database: str = "INFO"
    loglevel_model: str = "INFO"
    loglevel_preloader: str = "INFO"
    loglevel_contract_activation: str = "INFO"
    loglevel_realtime_sync_events: str = "INFO"
    loglevel_constant_prediction: str = "INFO"
    loglevel_path_evaluation: str = "INFO"

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


__doc__=f"""Start model runner.

Usage: bofh.model.runner [options]

Options:
  -h  --help
  -d, --status_db_dsn=<connection_str>      DB status dsn connection string. Default is {Args.status_db_dsn}
  --reports_db_dsn=<connection_str>         DB reports dsn connection string. Default is {Args.reports_db_dsn}
  --attacks_db_dsn=<connection_str>         DB reports dsn connection string. Default is {Args.attacks_db_dsn}
  -c, --web3_rpc_url=<url>                  Web3 RPC connection URL. Default is {Args.web3_rpc_url}
  -j, --max_workers=<n>                     number of RPC data ingest workers, default one per hardware thread. Default is {Args.max_workers}
  -v, --verbose                             debug output
  --chunk_size=<n>                          preloaded work chunk size per each worker Default is {Args.chunk_size}
  --pred_polling_interval=<n>               Web3 prediction polling internal in millisecs. Default is {Args.pred_polling_interval}
  --start_token_address=<address>           on-chain address of start token. Default is {Args.start_token_address}
  --max_reserves_snapshot_age_secs=<s>      max age of usable LP reserves DB snapshot (refuses to preload from DB if older). Default is {Args.max_reserves_snapshot_age_secs}
  --force_reuse_reserves_snapshot           disregard --max_reserves_snapshot_age_secs (use for debug purposes, avoids download of reserves)       
  --do_not_update_reserves_from_chain       do not attempt to forward an existing reserves DB snapshot to the latest known block
  --contract_address=<address>              set contract counterpart address. Default is {Args.contract_address}
  --wallet_address=<address>                funding wallet address. Default is {Args.wallet_address}
  --wallet_password=<pass>                  funding wallet address. Default is  {Args.wallet_password}
  --initial_amount_min=<wei>                min initial amount of start_token considered for swap operation. Default is {Args.initial_amount_min}
  --initial_amount_max=<wei>                max initial amount of start_token considered for swap operation. Default is {Args.initial_amount_max}
  --path_estimation_amount=<wei>            amount used for initial exploratory search of profitable paths. Default is {Args.path_estimation_amount}
  --min_profit_target_ppm=<ppM>             minimum viable profit target in parts per million (relative). Default is {Args.min_profit_target_ppm}
  --max_profit_target_ppm=<ppM>             minimum viable profit target in parts per million (relative). Default is {Args.max_profit_target_ppm}
  --min_profit_target_amount=<wei>          minimum viable profit target in wei (absolute). Default is {Args.min_profit_target_amount}
  --attacks_mute_cache_size=<n>             size of the known attacks mute cache. Default is {Args.attacks_mute_cache_size}
  --attacks_mute_cache_deadline=<secs>      expunge time deadline of the known attacks mute cache. Default is {Args.attacks_mute_cache_deadline} 
                                            Spotted attacks are put in the mute cache unless successfully exploited, 
                                            not to be noticed repeated again unless they are expunged via cache size or time limits.
  --dry_run                                 call contract execution to estimate outcome without actual transaction (no-risk no-reward mode)
  --dry_run_delay=<secs>                    delay seconds from opportunity spotting and arbitrage simulation. Default is {Args.dry_run_delay}
  --logfile=<file>                          log to file
  --loglevel_runner=<level>                 set subsystem loglevel. Default is INFO
  --loglevel_database=<level>               set subsystem loglevel. Default is INFO
  --loglevel_model=<level>                  set subsystem loglevel. Default is INFO
  --loglevel_preloader=<level>              set subsystem loglevel. Default is INFO
  --loglevel_contract_activation=<level>    set subsystem loglevel. Default is INFO
  --loglevel_realtime_sync_events=<level>   set subsystem loglevel. Default is INFO
  --loglevel_constant_prediction=<level>    set subsystem loglevel. Default is INFO
  --loglevel_path_evaluation=<level>        set subsystem loglevel. Default is INFO
  --cli                                     preload status and stop at CLI (for debugging)
"""

log = Loggers.runner


class Runner(TheGraph
             , EntitiesPreloader
             , ConstantPrediction
             , SyncEventRealtimeTracker
             , ContractCalling
             ):

    def __init__(self, args: Args):
        EntitiesPreloader.__init__(self)
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        self.reports_db = ModelDB(schema_name="reports", cursor_factory=StatusScopedCursor, db_dsn=self.args.reports_db_dsn)
        self.reports_db.open_and_priming()
        self.attacks_db = ModelDB(schema_name="attacks", cursor_factory=StatusScopedCursor, db_dsn=self.args.attacks_db_dsn)
        self.attacks_db.open_and_priming()
        ContractCalling.__init__(self, args=self.args)
        TheGraph.__init__(self, self.db, attacks_db=self.attacks_db)
        self.ioloop = get_event_loop()
        self.consistency_checks()
        self.status_lock = Lock()
        self.reserves_update_batch = list()  # reserve0, reserve1, tag
        self.reserves_update_blocknr = 0
        self.delayed_executor = DelayedExecutor(self)
        self.attack_ctr = 0
        self.attack_last_ts = 0
        self.attack_attempts = set()
        # self.polling_started = Event()

    def consistency_checks(self):
        log.info("Runtime parameter map:")
        for f in fields(self.args):
            v = getattr(self.args, f.name)
            if f.name.find("password") > 0:
                v = "*" * len(v)
            log.info(" \\____ %s = %s", f.name, v)
        try:
            contract_balance = self.contract_balance()
            log.info("contract at %s has %u in balance", self.args.contract_address, contract_balance)
            if contract_balance < self.args.initial_amount_max or contract_balance < self.args.initial_amount_min:
                log.error("financial attack parameters ( --initial_amount_min=%r and --initial_amount_max=%r "
                               ") are not compatible with contract balance"
                               , self.args.initial_amount_min
                               , self.args.initial_amount_max)
        except:
            log.error("unable to read current balance for contract at %s", self.args.contract_address)

    def check_all_paths(self):
        constraint = self.get_constraints()
        contract = self.get_contract()
        matches = self.graph.debug_evaluate_known_paths(constraint)
        for i, attack_plan in enumerate(matches):
            if constraint.match_limit and i >= constraint.match_limit:
                return
            new_entry = self.post_attack_to_db(attack_plan=attack_plan
                                                     , contract=contract
                                                     , origin="sweep")
            if not new_entry:
                log.debug("match having path id %r is already in mute_cache. "
                          "activation inhibited", attack_plan.id())

    def preflight_check(self, attack_plan):
        try:
            c_address = to_checksum_address(self.args.contract_address)
            w_address = to_checksum_address(self.args.wallet_address)
            call_args = self.path_attack_payload(attack_plan=attack_plan
                                                 , allow_net_losses=False
                                                 , allow_break_even=True)
            final_amount = self.call(function_name="multiswapd"
                      , from_address=w_address
                      , to_address=c_address
                      , call_args=call_args)
            return True, None, final_amount

        except ContractLogicError as err:
            txt = str(err)
            if txt.find(":") > 0:
                txt = txt.split(":", 1)[1]
            txt = txt.strip()
            return False, txt, 0

    def execute_attack(self, attack_plan):
        good, err, final_amount = self.preflight_check(attack_plan)
        if not good:
            return good, err, final_amount
        try:
            log.info("engaging execution of attack %r, path id %r --> %s ..."
                     , attack_plan.tag
                     , attack_plan.id()
                     , attack_plan.path.get_symbols() )
            c_address = to_checksum_address(self.args.contract_address)
            w_address = to_checksum_address(self.args.wallet_address)
            call_args = self.path_attack_payload(attack_plan=attack_plan
                                                 , allow_net_losses=False
                                                 , allow_break_even=True)
            txRecepit = self.transact_and_wait(function_name="multiswapd"
                      , from_address=w_address
                      , to_address=c_address
                      , call_args=call_args)
            return True, txRecepit
        except ContractLogicError as err:
            txt = str(err)
            if txt.find(":") > 0:
                txt = txt.split(":", 1)[1]
            txt = txt.strip()
            return False, txt

    def execute_attack_(self, attack_plan):
        good, err, final_amount = self.preflight_check(attack_plan)
        if good:
            pass

        return
        try:
            with self.attacks_db as curs:
                i = curs.get_attack(id)
                if i.path_id in self.attack_attempts: return
                if self.attack_last_ts > time() - 3600: return
                log.info("performing preflight check on attack %r...", id)
                good, err = self.preflight_check(i)
                if not (good or err == "MP"): # Missed profit
                    log.warn("not attempting attack %r since it would fail: %s", id, err)
                    return
                self.attack_last_ts = time()
                self.attack_attempts.add(i.path_id)
                c_address = to_checksum_address(self.args.contract_address)
                w_address = to_checksum_address(self.args.wallet_address)
                self.unlock_wallet(w_address, self.args.wallet_password)
                gas = self.estimate_gas(
                    function_name="multiswap"
                    , from_address=w_address
                    , to_address=c_address
                    , call_args=self.path_attack_payload(i, expectedAmount=0)
                )
                log.info("attempting attack %r... (gas=%r)", id, gas)
                receipt = self.transact_and_wait(
                    function_name="multiswap"
                    , from_address=w_address
                    , to_address=c_address
                    , call_args=self.path_attack_payload(i)
                    , gas=gas
                )
                log.debug("transaction receipt received. tx hash = %s", receipt["blockHash"].hex())
        except:
            log.exception("Error during execution of attack %r", id)

    def get_constraints(self):
        constraint = PathEvalutionConstraints()
        constraint.initial_balance_min = self.args.initial_amount_min
        constraint.initial_balance_max = self.args.initial_amount_max
        if self.args.min_profit_target_ppm:
            constraint.convenience_min_threshold = (1000000+self.args.min_profit_target_ppm)/1000000
        if self.args.max_profit_target_ppm:
            constraint.convenience_max_threshold = (1000000+self.args.max_profit_target_ppm)/1000000
        if self.args.min_profit_target_amount:
            constraint.min_profit_target_amount = self.args.min_profit_target_amount
        return constraint

    def on_profitable_path_execution(self, match):
        log = Loggers.runner
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
            log.info("SUCCESS: initialAmount=%u %u-way swap yields %u (%d gain, or %0.3f%%)"
                          , initialAmount
                          , len(pools)
                          , yields
                          , yields-initialAmount
                          , (yields/initialAmount)*100.0
                          )
        except:
            log.exception("unable to execute dry-run contract estimation")

    def start(self):
        SyncEventRealtimeTracker.start(self)
        ConstantPrediction.start(self)

    def stop(self):
        SyncEventRealtimeTracker.stop(self)
        ConstantPrediction.stop(self)

    def join(self):
        SyncEventRealtimeTracker.join(self)
        ConstantPrediction.stop(self)



old_format = ColoredFormatter.format
def new_format(self, record):
    record.name = record.name.replace("bofh.model.", "")
    return old_format(self, record)
ColoredFormatter.format = new_format

def main():
    args = Args.from_cmdline(__doc__)
    log_set_level(log_level.debug)
    log_register_sink(Loggers.model)
    if args.logfile:
        basicConfig(
            filename=args.logfile,
            filemode="a",
            format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
            level="DEBUG",
        )
    else:
        import coloredlogs
        coloredlogs.install(level="DEBUG", datefmt='%Y%m%d%H%M%S')
    if not getattr(args, "verbose", 0):
        # limit debug log output to bofh.* loggers
        filter = Filter(name="bofh")
        for h in getLogger().handlers:
            h.addFilter(filter)
    bofh = Runner(args)
    bofh.load(only_inspected_tokens=True)
    if args.cli:
        from IPython import embed
        while True:
            embed()
    bofh.start()
    bofh.join()


if __name__ == '__main__':
    main()
