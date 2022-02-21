import asyncio
from functools import lru_cache
from json import dump
from pprint import pprint
from threading import Lock
from time import strftime, gmtime

from eth_utils import to_checksum_address
from jsonrpc_websocket import Server
from tabulate import tabulate
from web3.exceptions import ContractLogicError

from bofh.model.modules.cached_entities import CachedEntities
from bofh.model.modules.constants import  ENV_SWAP_CONTRACT_ADDRESS, ENV_BOFH_WALLET_ADDRESS, \
    ENV_BOFH_WALLET_PASSWD
from bofh.model.modules.contract_calls import ContractCalling
from bofh.model.modules.loggers import Loggers
from bofh.utils.web3 import Web3Connector, JSONRPCConnector

from dataclasses import dataclass, fields, MISSING
from logging import basicConfig, Filter, getLogger

from bofh.model.database import ModelDB, StatusScopedCursor, Intervention


# add bofh.contract/contracts to get_abi() seach path:

@dataclass
class Args:
    status_db_dsn: str = "sqlite3://status.db"
    attacks_db_dsn: str = "sqlite3://attacks.db"
    verbose: bool = False
    web3_rpc_url: str = JSONRPCConnector.connection_uri()
    contract_address: str = ENV_SWAP_CONTRACT_ADDRESS
    wallet_address: str = ENV_BOFH_WALLET_ADDRESS
    wallet_password: str = ENV_BOFH_WALLET_PASSWD
    dry_run: bool = False
    logfile: str = None
    loglevel_runner: str = "INFO"
    loglevel_database: str = "INFO"
    loglevel_model: str = "INFO"
    loglevel_contract_activation: str = "INFO"
    order_by: str = "latest"
    asc: bool = False
    limit: int = 0
    list: bool = False
    untouched: bool = False
    failed: bool = False
    successful: bool = False
    yield_max: float = None
    yield_min: float = None
    describe: int = None
    print_calldata: bool = False
    weis: bool = False
    check: bool = False
    execute: int = None
    initial_amount: int = None
    min_gain_amount: int = None
    min_gain_ppm: int = None
    fees_ppm: int = None
    yes: bool = False
    allow_net_losses: bool = False

    DB_CACHED_PARAMETERS = {
        # List of parameters which are also stored in DB in a stateful manner
        "web3_rpc_url",
        "contract_address",
        "wallet_address",
        "wallet_password",
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
        if key.startswith("loglevel_"):
            ln = key[9:]
            logger = getattr(Loggers, ln, None)
            if logger:
                value = str(value).upper()
                logger.setLevel(value)
        super(Args, self).__setattr__(key, value)
        if key not in self.DB_CACHED_PARAMETERS:
            return
        db = getattr(self, "db", None)
        if not db:
            return
        with db as curs:
            curs.set_meta(key, value)


__doc__=f"""Browse, test and operate financial attacks.

Usage: bofh.model.attack [options]

Options:
  -h  --help
  -d, --status_db_dsn=<connection_str>    DB status dsn connection string. Default is {Args.status_db_dsn}
  --attacks_db_dsn=<connection_str>       DB reports dsn connection string. Default is {Args.attacks_db_dsn}
  -c, --web3_rpc_url=<url>                Web3 RPC connection URL. Default is {Args.web3_rpc_url}
  -v, --verbose                           debug output
  --wallet_address=<address>              funding wallet address. Default from BOFH_WALLET_ADDRESS envvar
  --wallet_password=<pass>                funding wallet address. Default from BOFH_WALLET_PASSWD envvar
  
  -l, --list                              print LIST of financial attacks.
  When using --list, these options are also apply:
    -o, --order_by=<attribute>            latest, yield. Default is {Args.order_by}
    -n, --limit=<n>                       latest, yield. Default is {Args.limit}
    --untouched                           only list untouched attacks. Omit previously attempted attacks
    --failed                              list executed failed attacks
    --successful                          list executed successful attacks
    --yield_min=<percent>                 filter by minimum target yield percent (1 means 1% gain). Default is {Args.yield_min}
    --yield_max=<percent>                 filter by minimum target yield percent (1 means 1% gain). Default is {Args.yield_max}
 
  --describe=<id>                         describe a swap attack in its inferred details.
  When using --describe, these options also apply:
    --print_calldata                      Print complete calldata string
    --weis                                Also print amounts in wei units
    --check                               Perform preflight check to estimate success likelyhood
  
  -x, --execute=<id>                      run an attack and wait for results (better test first with --dry-run)
  When using --execute, these options also apply:
    -n, --dry_run                         call contract execution to estimate outcome without actual transaction (no-risk no-reward mode)
    --initial_amount=<wei>                override initial wei amount. Default from specified attack record
    --min_gain_amount=<wei>               override minimum gain wei amount. Default from specified attack record
    --min_gain_ppm=<ppm>                  override minimum gain in parts per million. Default from specified attack record
    --fees_ppm=<ppm>                      override swap fees (parts per million. Ex: 2500 means 0.25%)
    --contract_address=<address>          set contract counterpart address. Default Default from specified attack record
    -y, --yes                             do not ask for confirmation
    --allow_net_losses                    allow the financial attack to result in a net loss without rolling back the transaction (use this for debug only!)

Logging options:  
  --logfile=<file>                        log to file
  --loglevel_runner=<level>               set subsystem loglevel. Default is INFO
  --loglevel_database=<level>             set subsystem loglevel. Default is INFO
  --loglevel_model=<level>                set subsystem loglevel. Default is INFO
  --loglevel_constant_prediction=<level>  set subsystem loglevel. Default is INFO
"""

log = getLogger("bofh.model.attack")

class ManagedAbort(RuntimeError): pass


def prompt(args: Args, msg):
    if not args.yes:
        print("%s [y/N]" % msg)
        yes = {'yes', 'y', 'ye'}

        choice = input().lower()
        if choice in yes:
            return True
        raise ManagedAbort("Bailing out due to user choice")


class Attack(ContractCalling, CachedEntities):
    def __init__(self, args: Args):
        ContractCalling.__init__(self)
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        CachedEntities.__init__(self, self.db)
        self.attacks_db = ModelDB(schema_name="attacks", cursor_factory=StatusScopedCursor, db_dsn=self.args.attacks_db_dsn)
        self.attacks_db.open_and_priming()
        self.args.sync_db(self.db)
        self.status_lock = Lock()
        self.tokens = {}
        self.pools = {}
        self.exchanges = {}
        self.args.sync_db(self.db)

    def __call__(self, *args, **kwargs):
        try:
            if self.args.list:
                self.list()
            elif self.args.describe:
                self.describe(self.args.describe)
            elif self.args.execute:
                self.execute(self.args.execute)
            else:
                log.error("please specify a command: --list, --describe, --execute")
        except ManagedAbort as err:
            log.error(str(err))

    def get_path_short(self, i: Intervention):
        symbols = []
        for step in i.steps:
            s = self.get_token(address_or_id=step.tokenIn_addr)
            symbols.append(s.get_symbol() or s.address[0:8])
        symbols.append(symbols[0])
        return "-".join(symbols)

    def get_initial_token(self, i: Intervention):
        return self.get_token(address_or_id=i.steps[0].tokenIn_addr)

    def get_token_before_step(self, i: Intervention, n):
        return self.get_token(address_or_id=i.steps[n].tokenIn_addr)

    def get_token_after_step(self, i: Intervention, n):
        return self.get_token(address_or_id=i.steps[n].tokenOut_addr)

    def get_intervention(self, id, patch=False):
        with self.attacks_db as curs:
            i = curs.get_intervention(id)
            if patch:
                if self.args.fees_ppm:
                    for s in i.steps:
                        s.feePPM = self.args.fees_ppm
                if self.args.initial_amount:
                    i.amountOut = i.amountIn = self.args.initial_amount
                if self.args.min_gain_amount:
                    new = i.amountIn + self.args.min_gain_amount
                    i.amountOut = max(i.amountOut, new)
                if self.args.min_gain_ppm:
                    new = int(i.amountIn * (1000000+self.args.min_gain_ppm) / 1000000)
                    i.amountOut = max(i.amountOut, new)
                if self.args.allow_net_losses:
                    i.amountOut = 0
            return i

    def list(self):
        direction = self.args.asc and "ASC" or "DESC"
        if self.args.order_by == "latest":
            order_by = "ORDER BY origin_ts"
        elif self.args.order_by == "yield":
            order_by = "ORDER BY yieldRatio"
        else:
            raise RuntimeError("invalid order_by value: %s" % self.args.order_by)
        limit = ""
        if self.args.limit:
            limit = "LIMIT %u" % self.args.limit
        wheres_or = list()
        wheres_and = list()
        args = list()

        if self.args.untouched:
            wheres_or.append("id NOT IN (SELECT fk_intervention FROM intervention_outcomes)")
        if self.args.failed:
            wheres_or.append("id IN (SELECT fk_intervention FROM intervention_outcomes WHERE outcome = 'failed')")
        if self.args.successful:
            wheres_or.append("id IN (SELECT fk_intervention FROM intervention_outcomes WHERE outcome = 'ok')")
        if self.args.yield_min:
            wheres_and.append("yieldRatio >= ?")
            args.append(1 + (float(self.args.yield_min) / 100))
        if self.args.yield_max:
            wheres_and.append("yieldRatio <= ?")
            args.append(1 + (float(self.args.yield_max) / 100))

        where = "WHERE 1=1"
        if wheres_or:
            where += " AND (%s)" % (" OR ").join(wheres_or)
        if wheres_and:
            where += " AND (%s)" % (" AND ").join(wheres_and)
        sql = f"SELECT id FROM interventions {where} {order_by} {direction} {limit}"
        with self.attacks_db as curs:
            headers = ["id", "path", "len", "block#", "yield%", "initial", "final"]
            if self.args.check:
                headers.append("good?")
            table = []
            for id, in list(curs.execute(sql, args).get_all()):
                i = self.get_intervention(id, patch=False)
                initial_token = self.get_initial_token(i)
                row = [i.tag
                              , self.get_path_short(i)
                              , len(i.steps)
                              , i.blockNr
                              , "%0.4f"%i.yieldPercent
                              , self.amount_hr(i.amountIn, initial_token)
                              , self.amount_hr(i.amountOut, initial_token)]
                if self.args.check:
                    i = self.get_intervention(id, patch=True)
                    good, err = self.preflight_check(i)
                    if good:
                        row.append("OK")
                    else:
                        row.append("ERR:%s"%err)
                table.append(row)
            print(tabulate(table, headers=headers, tablefmt="orgtbl"))

    def describe(self, attack_id):
        i = self.get_intervention(attack_id, patch=False)
        initial_token = self.get_initial_token(i)
        print( "Description of financial attack %r" % i.tag)
        print( "   \\___ this is a %u-way swap" % len(i.steps))
        print(f"   \\___ detection origin is {i.origin} at block {i.blockNr}")
        ots = strftime("%c UTC", gmtime(int(i.origin_ts)))
        print(f"   \\___ origin timestamp is {ots} (unix_time={i.origin_ts})")
        hr_amountin = self.amount_hr(i.amountIn, initial_token)
        hr_amountout = self.amount_hr(i.amountOut, initial_token)
        weis = ""
        if self.args.weis:
            weis = f"({i.amountIn} weis)"
        print(f"   \\___ attack estimation had {hr_amountin} {initial_token.get_symbol()} of input balance {weis}")
        print(f"   \\___ estimated yield was {hr_amountout} {initial_token.get_symbol()} ({i.amountOut} weis)")
        print(f"   \\___ path unique identifier is {i.path_id}")
        print(f"   \\___ target BOfH contract is {i.contract}")
        if self.args.print_calldata:
            print(f"         \\___ calldata is {i.calldata}")
        print(f"   \\___ detail of the path traversal:")
        print(f"       \\___ initial balance is {hr_amountin} of {initial_token.get_symbol()} (token {initial_token.address})")
        last_exc = None
        for si, step in enumerate(i.steps):
            pool = self.get_pool(address=step.pool_addr)
            exc = self.get_exchange(pool.exchange_id)
            if exc != last_exc:
                last_exc = exc
                part = f"is sent to exchange {exc.name}"
            else:
                part = f"stays on exchange {exc.name}"
            pn = self.get_pool_name(pool)
            token_in = self.get_token_before_step(i, si)
            token_out = self.get_token_after_step(i, si)
            hr_amountin = self.amount_hr(step.amountIn, token_in)
            hr_amountout = self.amount_hr(step.amountOut, token_out)
            t0, t1 = self.get_pool_tokens(pool)
            hr_r0 = self.amount_hr(step.reserve0, t0)
            hr_r1 = self.amount_hr(step.reserve1, t1)
            print(f"       \\___ this {part} via pool {pn} ({pool.address})")
            print(f"       |     \\___ this pool stores:")
            print(f"       |     |     \\___ reserve0 is ~= {hr_r0} {t0.get_symbol()}")
            if self.args.weis:
                print(f"       |     |     |     \\___ or ~= {step.reserve0} weis of token {t0.address} ")
            print(f"       |     |     \\___ reserve1 is ~= {hr_r1} {t1.get_symbol()}")
            if self.args.weis:
                print(f"       |     |           \\___ or ~= {step.reserve1} weis of token {t1.address} ")
            weis = ""
            if self.args.weis:
                weis = f" ({step.amountIn} weis)"
            print(f"       |     \\___ the swaps sends in {hr_amountin}{weis} of {token_in.get_symbol()}")
            weis = ""
            if self.args.weis:
                weis = f" ({step.amountOut} weis)"
            print(f"       |     \\___ and exchanges to {hr_amountout}{weis} of {token_out.get_symbol()}")
            print( "       |           \\___ effective rate of change is %0.5f %s-%s" % (step.amountOut/step.amountIn, token_out.get_symbol(), token_in.get_symbol()))
            print( "       |           \\___ this includes a %0.4f%% swap fee" % (step.feePPM/10000))
        print(f"       \\___ final balance is {hr_amountout} of {initial_token.get_symbol()} (token {initial_token.address})")
        gap = i.amountOut - i.amountIn
        if gap > 0:
            hr_g = self.amount_hr(gap, initial_token)
            gain = f"net gain of {hr_g} {initial_token.get_symbol()}"
            if self.args.weis:
                gain += f" (+{gap} weis)"
        else:
            gap = -gap
            hr_g = self.amount_hr(gap, initial_token)
            gain = f"net loss of {hr_g} {initial_token.get_symbol()}"
            if self.args.weis:
                gain += f" (-{gap} weis)"
        print(f"           \\___ this results in a {gain}")
        print( "                 \\___ which is a %0.4f%% net yield" % i.yieldPercent)

    def execute(self, attack_id):
        self.describe(attack_id)
        prompt(self.args, f"Execute attack {attack_id}?")
        i = self.get_intervention(attack_id, patch=True)
        initial_token = self.get_initial_token(i)
        hr_amountin = self.amount_hr(i.amountIn, initial_token)
        hr_amountout = self.amount_hr(i.amountOut, initial_token)
        log.info(f"prospected attack balance for attack is {hr_amountin} {initial_token.get_symbol()} ({i.amountIn} weis), "
                 f"final balance would be {hr_amountout} {initial_token.get_symbol()}")
        res = input(f"Override attack balance? [{i.amountIn}]")
        if res:
            i.amountIn = eval(res)
            hr_amountin = self.amount_hr(i.amountIn, initial_token)
            log.info(f"new attack balance is {hr_amountin} {initial_token.get_symbol()} ({i.amountIn} weis)")
        log.info("performing preflight check...")
        good, err = self.preflight_check(i)
        if not good:
            raise ManagedAbort("preflight check failed: %s" % err)

        c_address = to_checksum_address(self.args.contract_address)
        w_address = to_checksum_address(self.args.wallet_address)
        self.unlock_wallet(w_address, self.args.wallet_password)
        receipt = self.transact_and_wait(
            function_name="multiswap"
            , from_address=w_address
            , to_address=c_address
            , call_args=self.pack_intervention_payload(i)
        )
        log.debug("transaction receipt received. tx hash = %s", receipt["blockHash"].hex())
        if False:

            async def trace_call():
                server = Server(self.args.web3_rpc_url)
                await server.ws_connect()
                res = await server.debug_traceCall({"from": w_address, "to": c_address, "data": i.calldata}, "latest")
                with open("coso.json", "w") as fd:
                    dump(res, fd)

            from asyncio import get_event_loop
            ioloop = get_event_loop()
            ioloop.run_until_complete(trace_call())


    def preflight_check(self, i: Intervention):
        try:
            c_address = to_checksum_address(self.args.contract_address)
            w_address = to_checksum_address(self.args.wallet_address)
            self.call(function_name="multiswap"
                      , from_address=w_address
                      , to_address=c_address
                      , call_args=self.pack_intervention_payload(i))
            return True, None
        except ContractLogicError as err:
            txt = str(err)
            txt = txt.replace("Pancake: ", "")
            txt = txt.replace("BOFH:", "")
            txt = txt.replace("execution reverted:", "")
            if txt == "K":
                txt = "WRONG_RATIO"
            return False, txt

    def pack_intervention_payload(self, i: Intervention):
        pools = []
        fees = []
        initialAmount = i.amountIn
        expectedAmount = i.amountOut

        if self.args.allow_net_losses:
            expectedAmount = 0
        if self.args.initial_amount:
            initialAmount = self.args.initial_amount
        for step in i.steps:
            pools.append(to_checksum_address(step.pool_addr))
            if self.args.fees_ppm:
                fees.append(self.args.fees_ppm)
            else:
                fees.append(step.feePPM)
        return self.pack_args_payload(pools=pools
                                      , fees=fees
                                      , initialAmount=initialAmount
                                      , expectedAmount=expectedAmount)


def main():
    args = Args.from_cmdline(__doc__)
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
    bofh = Attack(args)
    bofh()


if __name__ == '__main__':
    main()
