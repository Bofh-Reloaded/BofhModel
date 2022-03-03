from time import strftime, gmtime

from eth_utils import to_checksum_address
from tabulate import tabulate
from web3.exceptions import ContractLogicError

from bofh.model.modules.constants import  ENV_SWAP_CONTRACT_ADDRESS, ENV_BOFH_WALLET_ADDRESS, \
    ENV_BOFH_WALLET_PASSWD
from bofh.model.modules.contract_calls import ContractCalling
from bofh.model.modules.loggers import Loggers
from bofh.utils.web3 import JSONRPCConnector

from dataclasses import dataclass, fields, MISSING
from logging import basicConfig, Filter, getLogger

from bofh.model.modules.graph import TheGraph
from bofh.model.database import ModelDB, StatusScopedCursor


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
    origin_tx: bool = False
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
    allow_break_even: bool = False
    fetch_reserves: bool = False


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
    --origin_tx                           display origin (trigger) tx
    --fetch_reserves                      use pool reserves obtained via web3 (fresh data!)
 
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
    --contract_address=<address>          set contract counterpart address. Default from specified attack record
    -y, --yes                             do not ask for confirmation
    --allow_net_losses                    allow the financial attack to result in a net loss without rolling back the transaction (use this for debug only!)
    --allow_break_even                    allow the financial attack to result in a net break-even without rolling back the transaction (use this for debug only!)

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


class Attack(ContractCalling, TheGraph):
    def __init__(self, args: Args):
        self.args = args
        self.db = ModelDB(schema_name="status"
                          , cursor_factory=StatusScopedCursor
                          , db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        self.attacks_db = ModelDB(schema_name="attacks"
                                  , cursor_factory=StatusScopedCursor
                                  , db_dsn=self.args.attacks_db_dsn)
        self.attacks_db.open_and_priming()
        self.args.sync_db(self.db)
        ContractCalling.__init__(self, args=args)
        TheGraph.__init__(self, self.db, attacks_db=self.attacks_db)
        if self.args.fetch_reserves:
            # override reserves fetch routine
            self.graph.set_fetch_lp_reserves_tag_cb(self.fetch_reserves)

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

    def fetch_reserves(self, pool):
        contract = self.get_contract(str(pool.address), abi="IGenericLiquidityPool")
        callable = contract.functions.getReserves()
        r0, r1, _ = callable.call()
        pool.setReserves(r0, r1)
        return pool

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
        sql = f"SELECT id, path_id, blockNr, origin_tx " \
              f"FROM interventions {where} {order_by} {direction} {limit}"
        with self.attacks_db as curs:
            headers = ["id", "path", "len", "yield%", "block#"]
            if self.args.origin_tx:
                headers.append("tx")
            if self.args.check:
                headers.append("good?")
            table = []
            for id, path_id, blockNr, origin_tx in list(curs.execute(sql, args).get_all()):
                path = self.graph.lookup_path(int(path_id))
                constraints = self.get_constraint(path.initial_token())
                result = path.evaluate(constraints, False)
                yieldPercent = 100.0*(result.yield_ratio()-1.0)
                row = [id
                       , path.get_symbols()
                       , path.size()
                       , "%0.4f"%yieldPercent
                       , blockNr
                       ]
                if self.args.origin_tx:
                    row.append(origin_tx or "")
                if self.args.check:
                    good, err = self.preflight_check(path
                                                     , int(str(result.initial_balance()))
                                                     , int(str(result.final_balance())))
                    if good:
                        row.append("OK")
                    else:
                        row.append("ERR: %s"%err)
                table.append(row)
            print(tabulate(table, headers=headers, tablefmt="orgtbl"))

    def get_constraint(self, initial_token):
        res = super(Attack, self).get_constraint()
        if self.args.initial_amount:
            res.initial_token_wei_balance = self.args.initial_amount
        else:
            res.initial_token_wei_balance = 10 ** initial_token.decimals
        return res

    def find_best_amount(self, path, amount_min, amount_max):
        amount_min = int(str(amount_min))
        amount_max = int(str(amount_max))
        c = super(Attack, self).get_constraint()

        def yield_with_amount(amount):
            c.initial_token_wei_balance = amount
            result = path.evaluate(c, False)
            return int(str(result.final_balance())) \
                   - int(str(result.initial_balance()))

        fractions = 1000
        step = int((amount_max-amount_min) / fractions)

        base = amount_min
        y0 = yield_with_amount(base)
        y1 = yield_with_amount(base + step)
        if y0 < y1:
            find_max_from_base()
        if y0 > y1:
            find_max_from_top()

        if init > nxt:
            return amount_min
        nxt2 = yield_with_amount(amount_min + step*2)
        if nxt > nxt2:
            return amount_min + step
        nxt3 = yield_with_amount(amount_min + step*3)
        if nxt2 > nxt3:
            return amount_min + step*2

        return
        step = (amount_max - amount_min) // 50
        data = []
        for i in range(50):
            a = amount_min+i*step
            y = yield_with_amount(a)
            data.append([str(a), str(y)])
        print(tabulate(data))
        return
        amount_mid = int((amount_max + amount_min) / 2)
        a = yield_with_amount(amount_min)
        mid = yield_with_amount(amount_mid)
        b = yield_with_amount(amount_max)
        print(amount_mid, a)
        print(amount_mid, mid)
        print(amount_max, b)

    def describe(self, attack_id):
        with self.attacks_db as curs:
            path_id, origin, blockNr, origin_tx, origin_ts, calldata = \
                    curs.execute("SELECT path_id, origin, blockNr, origin_tx, origin_ts, calldata "
                                 "FROM interventions WHERE id = ?", (attack_id,)).get()
            path_id = int(path_id)
        path = self.graph.lookup_path(path_id)
        initial_token = path.initial_token()
        print( "Description of financial attack %r" % attack_id)
        print( "   \\___ this is a %u-way swap" % path.size())
        print(f"   \\___ detection origin is {origin} at block {blockNr}, tx {origin_tx}")
        ots = strftime("%c UTC", gmtime(int(origin_ts)))
        print(f"   \\___ origin timestamp is {ots} (unix_time={origin_ts})")
        constraint = self.get_constraint(initial_token)
        result = path.evaluate(constraint, False)
        hr_amountin = self.amount_hr(result.initial_balance(), initial_token)
        hr_amountout = self.amount_hr(result.final_balance(), initial_token)
        weis = ""
        if self.args.weis:
            weis = f"({result.initial_balance()} weis)"
        print(f"   \\___ attack estimation had {hr_amountin} {initial_token.symbol} of input balance {weis}")
        print(f"   \\___ estimated yield was {hr_amountout} {initial_token.symbol} ({result.final_balance()} weis)")
        print(f"   \\___ path unique identifier is {path.id()}")
        print(f"   \\___ target BOfH contract is {self.args.contract_address}")
        if self.args.print_calldata:
            print(f"         \\___ calldata is {calldata}")
        print(f"   \\___ detail of the path traversal:")
        print(f"       \\___ initial balance is {hr_amountin} of {initial_token.symbol} (token {initial_token.address})")
        last_exc = None
        for i in range(path.size()):
            swap = path.get(i)
            pool = swap.pool
            exc = pool.exchange
            if last_exc and exc.tag != last_exc.tag:
                last_exc = exc
                part = f"is sent to exchange {exc.name}"
            else:
                part = f"stays on exchange {exc.name}"
            token_in = result.token_before_step(i)
            token_out = result.token_after_step(i)
            amountIn = int(str(result.balance_before_step(i)))
            amountOut = int(str(result.balance_after_step(i)))
            hr_amountin = self.amount_hr(amountIn, token_in)
            hr_amountout = self.amount_hr(amountOut, token_out)
            rin, rout = int(str(pool.getReserve(token_in))), int(str(pool.getReserve(token_out)))
            hr_rin  = self.amount_hr(rin, token_in)
            hr_rout = self.amount_hr(rout, token_out)
            print(f"       \\___ this {part} via pool {pool.get_name()} ({pool.address})")
            print(f"       |     \\___ this pool stores:")
            print(f"       |     |     \\___ reserveIn is ~= {hr_rin} {token_in.symbol}")
            if self.args.weis:
                print(f"       |     |     |     \\___ or ~= {rin} weis of token {token_in.address} ")
            print(f"       |     |     \\___ reserveOut is ~= {hr_rout} {token_out.symbol}")
            if self.args.weis:
                print(f"       |     |           \\___ or ~= {rout} weis of token {token_out.address} ")
            weis = ""
            if self.args.weis:
                weis = f" ({amountIn} weis)"
            print(f"       |     \\___ the swaps sends in {hr_amountin}{weis} of {token_in.symbol}")
            weis = ""
            if self.args.weis:
                weis = f" ({amountOut} weis)"
            print(f"       |     \\___ and exchanges to {hr_amountout}{weis} of {token_out.symbol}")
            print( "       |           \\___ effective rate of change is %0.5f %s" % (amountOut/amountIn, pool.get_name()))
            print( "       |           \\___ this includes a %0.4f%% swap fee" % ((pool.feesPPM()/1000000)*100))
        print(f"       \\___ final balance is {hr_amountout} of {initial_token.symbol} (token {initial_token.address})")
        gap = int(str(result.final_balance())) - int(str(result.initial_balance()))
        yieldPercent = (result.yield_ratio()-1)*100
        if gap > 0:
            hr_g = self.amount_hr(gap, initial_token)
            gain = f"net gain of {hr_g} {initial_token.symbol}"
            if self.args.weis:
                gain += f" (+{gap} weis)"
        else:
            gap = -gap
            hr_g = self.amount_hr(gap, initial_token)
            gain = f"net loss of {hr_g} {initial_token.symbol}"
            if self.args.weis:
                gain += f" (-{gap} weis)"
        print(f"       |   \\___ this results in a {gain}")
        print( "       |         \\___ which is a %0.4f%% net yield" % yieldPercent)
        good, err = self.preflight_check(path
                                         , int(str(result.initial_balance()))
                                         , int(str(result.final_balance())))
        if good:
            txt = "SUCCESS"
        else:
            txt = f"ERR: {err}"
        print(f"       \\___ outcome of preflight check (using eth_call): {txt}")

    def execute(self, attack_id):
        with self.attacks_db as curs:
            path_id, = \
                curs.execute("SELECT path_id "
                             "FROM interventions WHERE id = ?", (attack_id,)).get()
            path_id = int(path_id)
        path = self.graph.lookup_path(path_id)
        self.describe(attack_id)
        prompt(self.args, f"Execute attack {attack_id}?")
        initial_token = path.initial_token()
        constraint = self.get_constraint(initial_token)
        trade_plan = path.estimate(constraint, False)
        amountIn = int(str(trade_plan.initial_balance()))
        amountOut = int(str(trade_plan.final_balance()))
        hr_amountin = self.amount_hr(amountIn, initial_token)
        hr_amountout = self.amount_hr(amountOut, initial_token)
        log.info(f"prospected attack balance for attack is {hr_amountin} {initial_token.symbol} ({amountIn} weis), "
                 f"final balance would be {hr_amountout} {initial_token.symbol}")
        res = input(f"Override attack balance? [{amountIn}]")
        if res:
            amountIn = eval(res)
            hr_amountin = self.amount_hr(amountIn, initial_token)
            log.info(f"new attack balance is {hr_amountin} {initial_token.symbol} ({amountIn} weis)")
        log.info("performing preflight check...")
        good, err = self.preflight_check(trade_plan.path, amountIn, amountOut)
        if not good:
            if err == "K":
                self.diagnose_k_error(trade_plan.path, amountIn, amountOut)
            raise ManagedAbort("preflight check failed: %s" % err)
        c_address = to_checksum_address(self.args.contract_address)
        w_address = to_checksum_address(self.args.wallet_address)
        if self.args.wallet_password:
            log.info("unlocking wallet %s", w_address)
            self.unlock_wallet(w_address, self.args.wallet_password)
        receipt = self.transact_and_wait(
            function_name="multiswap"
            , from_address=w_address
            , to_address=c_address
            , call_args=self.path_attack_payload(trade_plan.path, amountIn, amountOut)
        )
        log.debug("transaction receipt received. tx hash = %s", receipt["blockHash"].hex())

    def preflight_check(self, path, amountIn, expectedAmountOut):
        try:
            c_address = to_checksum_address(self.args.contract_address)
            w_address = to_checksum_address(self.args.wallet_address)
            self.call(function_name="multiswap"
                      , from_address=w_address
                      , to_address=c_address
                      , call_args=self.path_attack_payload(path, amountIn, expectedAmountOut))
            return True, None
        except ContractLogicError as err:
            txt = str(err)
            txt = txt.replace("Pancake: ", "")
            txt = txt.replace("BOFH:", "")
            txt = txt.replace("execution reverted:", "")
            txt = txt.strip()
            return False, txt

    def amount_hr(self, amount, token):
        return "%0.4f" % token.fromWei(amount)

    def diagnose_k_error(self, path, amountIn, expectedAmountOut):
        c_address = to_checksum_address(self.args.contract_address)
        w_address = to_checksum_address(self.args.wallet_address)
        for i in range(path.size()):
            try:
                res = self.call(function_name="multiswap"
                                , from_address=w_address
                                , to_address=c_address
                                , call_args=self.path_attack_payload(path
                                                                           , amountIn
                                                                           , expectedAmountOut
                                                                           , stop_after_pool=i) )
                print("pool[%u]: OK" % i, res)
            except ContractLogicError as err:
                txt = str(err)
                txt = txt.replace("Pancake: ", "")
                txt = txt.replace("BOFH:", "")
                txt = txt.replace("execution reverted:", "")
                txt = txt.strip()
                print("pool[%u]: %s" % (i, txt))

    def path_attack_payload(self, path, amountIn, expectedAmountOut, stop_after_pool=None):
        pools = []
        fees = []
        initialAmount = amountIn
        expectedAmount = expectedAmountOut
        if self.args.allow_net_losses:
            expectedAmount = 0
        if self.args.initial_amount:
            initialAmount = self.args.initial_amount
        if self.args.allow_break_even:
            expectedAmount = min(initialAmount, expectedAmount)
        for i in range(path.size()):
            swap = path.get(i)
            pools.append(str(swap.pool.address))
            if self.args.fees_ppm:
                fees.append(self.args.fees_ppm)
            else:
                fees.append(swap.pool.feesPPM())
        return self.pack_args_payload(pools=pools
                                      , fees=fees
                                      , initialAmount=initialAmount
                                      , expectedAmount=expectedAmount
                                      , stop_after_pool=stop_after_pool)


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
