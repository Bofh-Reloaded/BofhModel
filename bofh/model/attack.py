from time import strftime, gmtime

from eth_utils import to_checksum_address
from tabulate import tabulate
from web3.exceptions import ContractLogicError

from bofh.model.modules.contract_calls import ContractCalling

from dataclasses import dataclass, fields, MISSING
from logging import basicConfig, Filter, getLogger

from bofh.model.modules.graph import TheGraph
from bofh.model.database import ModelDB, StatusScopedCursor
from bofh_model_ext import log_set_level, log_level, log_register_sink


# add bofh.contract/contracts to get_abi() seach path:
from bofh.utils.config_data import BOFH_ATTACKS_DB_DSN, BOFH_STATUS_DB_DSN, BOFH_WEB3_RPC_URL, BOFH_CONTRACT_ADDRESS, \
    BOFH_WALLET_ADDRESS, BOFH_WALLET_PASSWD, BOFH_ATTACK_INITIAL_AMOUNT_MIN, BOFH_ATTACK_INITIAL_AMOUNT_MAX


@dataclass
class Args:
    status_db_dsn: str = BOFH_STATUS_DB_DSN
    attacks_db_dsn: str = BOFH_ATTACKS_DB_DSN
    verbose: bool = False
    web3_rpc_url: str = BOFH_WEB3_RPC_URL
    contract_address: str = BOFH_CONTRACT_ADDRESS
    wallet_address: str = BOFH_WALLET_ADDRESS
    wallet_password: str = BOFH_WALLET_PASSWD
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
    initial_amount_min: int = BOFH_ATTACK_INITIAL_AMOUNT_MIN
    initial_amount_max: int = BOFH_ATTACK_INITIAL_AMOUNT_MAX
    min_gain_amount: int = None
    min_gain_ppm: int = None
    fees_ppm: int = None
    yes: bool = False
    allow_net_losses: bool = False
    allow_break_even: bool = False
    reserves_from: str = "web3"
    find_optimal_amount: bool = False
    deflationary: bool = False

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

__doc__=f"""Browse, test and operate financial attacks.

Usage: bofh.model.attack [options]

Options:
  -h  --help
  -d, --status_db_dsn=<connection_str>    DB status dsn connection string. Default is {Args.status_db_dsn}
  --attacks_db_dsn=<connection_str>       DB reports dsn connection string. Default is {Args.attacks_db_dsn}
  -c, --web3_rpc_url=<url>                Web3 RPC connection URL. Default is {Args.web3_rpc_url}
  -v, --verbose                           debug output
  --wallet_address=<address>              funding wallet address. Default is {Args.wallet_address}
  --wallet_password=<pass>                funding wallet address. Default is {Args.wallet_password}
  
  -l, --list                              print LIST of financial attacks.
  When using --list, these options are also apply:
    -o, --order_by=<attribute>            latest, yield. Default is {Args.order_by}
    -n, --limit=<n>                       limit list length. Default is {Args.limit}
    --untouched                           only list untouched attacks. Omit previously attempted attacks
    --failed                              list executed failed attacks
    --successful                          list executed successful attacks
    --yield_min=<percent>                 filter by minimum target yield percent (1 means 1% gain). Default is {Args.yield_min}
    --yield_max=<percent>                 filter by minimum target yield percent (1 means 1% gain). Default is {Args.yield_max}
    --origin_tx                           display origin (trigger) tx
    --reserves_from=<source>              use pool reserves obtained via "record" or "web3". Default is {Args.reserves_from} 
    --find_optimal_amount                 determine optimal initial amount, to maximize yield. Default is {Args.find_optimal_amount}
    --deflationary                        attempt swap with supporting deflationary tokens
 
  --describe=<id>                         describe a swap attack in its inferred details.
  When using --describe, these options also apply:
    --print_calldata                      Print complete calldata string
    --weis                                Also print amounts in wei units
    --check                               Perform preflight check to estimate success likelyhood
  
  -x, --execute=<id>                      run an attack and wait for results (better test first with --dry-run)
  When using --execute, these options also apply:
    -n, --dry_run                         call contract execution to estimate outcome without actual transaction (no-risk no-reward mode)
    --initial_amount_min=<wei>            Specify initial amount (min) boundary. Default is {Args.initial_amount_min}
    --initial_amount_max=<wei>            Specify initial amount (max) boundary. Default is {Args.initial_amount_max}
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

class Reserves: pass

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
        ContractCalling.__init__(self, args=args)
        TheGraph.__init__(self, self.db, attacks_db=self.attacks_db)
        #if self.args.fetch_reserves:
        #    # override reserves fetch routine
        #    self.graph.set_fetch_lp_reserves_tag_cb(self.fetch_reserves)

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

    def fetch_reserves_from_web3(self, pool):
        contract = self.get_contract(str(pool.address), abi="IGenericLiquidityPool")
        callable = contract.functions.getReserves()
        r0, r1, _ = callable.call()
        pool.setReserves(r0, r1)
        return pool

    def fetch_reserves_from_db(self, pool):
        with self.db as curs:
            vals = curs.get_lp_reserves_vals(pool.tag)
            try:
                pool.setReserves(*vals)
                return pool
            except:
                pass

    def update_pool_reserves(self, attack_id, path):
        for i in range(path.size()):
            pool = path.get(i).pool
            if self.args.reserves_from == "web3":
                self.fetch_reserves_from_web3(pool)
            elif self.args.reserves_from == "record":
                self.fetch_reserves_from_attack_plan(attack_id, pool)
            else:
                raise RuntimeError("valid values for --reserves_from are web3 and record")

    def fetch_reserves_from_attack_plan(self, attack_id, pool):
        with self.attacks_db as curs:
            curs.execute("SELECT reserve0, reserve1 "
                         "FROM attack_steps "
                         "WHERE pool_id = ? AND fk_attack = ?",
                         (pool.tag, attack_id))
            try:
                reserve0, reserve1 = curs.get()
                pool.setReserves(reserve0, reserve1)
                return pool
            except:
                pass

    def get_constraint(self, initial_token, amountIn):
        res = super(Attack, self).get_constraint()
        if self.args.initial_amount_min:
                res.initial_balance_min = self.args.initial_amount_min
        if self.args.initial_amount_max:
            res.initial_balance_max = self.args.initial_amount_max
        res.initial_balance = amountIn
        res.optimal_amount_search_sections=10000
        return res

    def evaluate_path(self, attack_id, path, amountIn):
        self.update_pool_reserves(attack_id, path)
        constraints = self.get_constraint(path.initial_token(), amountIn)
        if self.args.find_optimal_amount:
            return path.evaluate_max_yield(constraints, False)
        return path.evaluate(constraints, False)

    def list(self):
        direction = ""
        order_by = ""
        limit = ""
        if self.args.order_by != "yield":
            if self.args.order_by == "latest":
                order_by = "ORDER BY origin_ts"
            else:
                raise RuntimeError("invalid order_by value: %s" % self.args.order_by)
            if self.args.limit:
                limit = "LIMIT %u" % self.args.limit
            direction = self.args.asc and "ASC" or "DESC"
        wheres_or = list()
        wheres_and = list()
        args = list()

        if self.args.untouched:
            wheres_or.append("id NOT IN (SELECT fk_attack FROM attack_outcomes)")
        if self.args.failed:
            wheres_or.append("id IN (SELECT fk_attack FROM attack_outcomes WHERE outcome = 'failed')")
        if self.args.successful:
            wheres_or.append("id IN (SELECT fk_attack FROM attack_outcomes WHERE outcome = 'ok')")

        where = "WHERE 1=1"
        if wheres_or:
            where += " AND (%s)" % (" OR ").join(wheres_or)
        if wheres_and:
            where += " AND (%s)" % (" AND ").join(wheres_and)
        sql = f"SELECT id, path_id, blockNr, origin_tx, yieldRatio, amountIn " \
              f"FROM attacks {where} {order_by} {direction} {limit}"
        with self.attacks_db as curs:
            headers = ["id", "path", "len", "in", "yield%"]
            if self.args.origin_tx:
                headers.append("tx")
            if self.args.check:
                headers.append("good?")
            table = []
            for id, path_id, blockNr, origin_tx, yieldRatio, amountIn in list(curs.execute(sql, args).get_all()):
                path = self.graph.lookup_path(int(path_id), True)
                if not path:
                    print("Unable to rebuild swap path from its unique id:", path_id)
                    continue
                attack_plan = self.evaluate_path(id, path, amountIn=amountIn)
                row = [id
                       , path.get_symbols()
                       , path.size()
                       , self.amount_hr(attack_plan.initial_balance(), attack_plan.initial_token())
                       ]
                good, err = None, None
                if attack_plan.failed:
                    row.append("FAIL")
                else:
                    yield_ratio = attack_plan.yield_ratio()
                    if self.args.check:
                        good, err, final_balance = self.preflight_check(attack_plan)
                        if good:
                            yield_ratio = final_balance / int(str(attack_plan.initial_balance()))
                    if self.args.yield_min and yield_ratio < self.args.yield_min:
                        continue
                    if self.args.yield_max and yield_ratio > self.args.yield_max:
                        continue
                    yield_percent = 100.0*(yield_ratio-1.0)
                    row.append("%0.4f"%yield_percent)
                if self.args.origin_tx:
                    row.append(origin_tx or "")
                if self.args.check:
                    if good:
                        row.append("OK")
                    else:
                        row.append("ERR: %s"%err)
                table.append(row)
            if self.args.order_by == "yield":
                table.sort(key=lambda a: a[3] != "FAIL" and float(a[3]) or 0)
                if not self.args.asc:
                    table.reverse()
                if self.args.limit:
                    table = table[0:self.args.limit]
            print(tabulate(table, headers=headers, tablefmt="orgtbl"))

    def find_best_amount(self, path, amount_min, amount_max):
        amount_min = int(str(amount_min))
        amount_max = int(str(amount_max))
        c = super(Attack, self).get_constraint()

        def yield_with_amount(amount):
            c.initial_balance = amount
            result = path.evaluate(c, False)
            return int(str(result.final_balance())) \
                   - int(str(result.initial_balance()))

        fractions = 1000
        step = int((amount_max-amount_min) / fractions)

        base = amount_min
        y0 = yield_with_amount(base)
        print("yield with", base, "is", y0)
        while True:
            base_next = base + step
            y1 = yield_with_amount(base_next)
            print("yield with", base_next, "is", y1)
            if y0 > y1 or base >= amount_max:
                break
            y0 = y1
            base = base_next
        return base

    def describe(self, attack_id):
        with self.attacks_db as curs:
            path_id, origin, blockNr, origin_tx, origin_ts, amountIn = \
                    curs.execute("SELECT path_id, origin, blockNr, origin_tx, origin_ts, amountIn "
                                 "FROM attacks WHERE id = ?", (attack_id,)).get()
            path_id = int(path_id)
        path = self.graph.lookup_path(path_id)
        if not path:
            print("Unable to rebuild swap path from its unique id:", path_id)
            return
        initial_token = path.initial_token()
        attack_plan = self.evaluate_path(attack_id, path, amountIn=amountIn)
        if attack_plan.failed:
            print("Internal consistency or logic error during evaluation of path", path_id)
            return
        print( "Description of financial attack %r" % attack_id)
        print( "   \\___ this is a %u-way swap" % path.size())
        print(f"   \\___ detection origin is {origin} at block {blockNr}, tx {origin_tx}")
        ots = strftime("%c UTC", gmtime(int(origin_ts)))
        print(f"   \\___ origin timestamp is {ots} (unix_time={origin_ts})")
        hr_amountin = self.amount_hr(attack_plan.initial_balance(), initial_token)
        hr_amountout = self.amount_hr(attack_plan.final_balance(), initial_token)
        reserve_source = self.args.reserves_from

        weis = ""
        if self.args.weis:
            weis = f"({attack_plan.initial_balance()} weis)"
        print(f"   \\___ attack estimation had {hr_amountin} {initial_token.symbol} of input balance {weis}")
        print(f"   \\___ estimated yield was {hr_amountout} {initial_token.symbol} ({attack_plan.final_balance()} weis)")
        print(f"   \\___ estimation was conducted using pool reserves observation from: {reserve_source}")
        print(f"   \\___ path unique identifier is {path.id()}")
        print(f"   \\___ target BOfH contract is {self.args.contract_address}")
        if self.args.print_calldata:
            print(f"         \\___ calldata is {attack_plan.get_calldata(self.args.deflationary)}")
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
            token_in = attack_plan.token_before_step(i)
            token_out = attack_plan.token_after_step(i)
            amountIn = int(str(attack_plan.balance_before_step(i)))
            amountOut = int(str(attack_plan.balance_after_step(i)))
            hr_amountin = self.amount_hr(amountIn, token_in)
            hr_amountout = self.amount_hr(amountOut, token_out)
            rin, rout = int(str(pool.getReserve(token_in))), int(str(pool.getReserve(token_out)))
            hr_rin  = self.amount_hr(rin, token_in)
            hr_rout = self.amount_hr(rout, token_out)
            print(f"       \\___ this {part} via pool {pool.get_name()} ({pool.address})")
            print(f"       |     \\___ this pool stores:")
            print(f"       |     |     \\___ {reserve_source} reserveIn is ~= {hr_rin} {token_in.symbol}")
            if self.args.weis:
                print(f"       |     |     |     \\___ or ~= {rin} weis of token {token_in.address} ")
            print(f"       |     |     \\___ {reserve_source} reserveOut is ~= {hr_rout} {token_out.symbol}")
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
        gap = int(str(attack_plan.final_balance())) - int(str(attack_plan.initial_balance()))
        yieldPercent = (attack_plan.yield_ratio()-1)*100
        good, err = None, None
        if self.args.check:
            good, err, final_balance = self.preflight_check(attack_plan)
            if good:
                gap = final_balance - int(str(attack_plan.initial_balance()))
                yield_ratio = final_balance / int(str(attack_plan.initial_balance()))
                yieldPercent = (yield_ratio-1)*100
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
        if self.args.check:
            if good:
                txt = "SUCCESS"
            else:
                txt = f"ERR: {err}"
            print(f"       \\___ outcome of preflight check (using eth_call): {txt}")

    def execute(self, attack_id):
        with self.attacks_db as curs:
            path_id, amountIn, = \
                curs.execute("SELECT path_id, amountIn "
                             "FROM attacks WHERE id = ?", (attack_id,)).get()
            path_id = int(path_id)
        path = self.graph.lookup_path(path_id)
        self.describe(attack_id)
        prompt(self.args, f"Execute attack {attack_id}?")
        initial_token = path.initial_token()
        constraint = self.get_constraint(initial_token, amountIn)
        attack_plan = path.estimate(constraint, False)
        amountIn = int(str(attack_plan.initial_balance()))
        amountOut = int(str(attack_plan.final_balance()))
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
        good, err, final_balance = self.preflight_check(attack_plan)
        if not good:
            if err == "K":
                self.diagnose_k_error(attack_plan.path, amountIn, amountOut)
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
            , call_args=self.path_attack_payload(attack_plan.path, amountIn, amountOut)
        )
        log.debug("transaction receipt received. tx hash = %s", receipt["blockHash"].hex())

    def preflight_check(self, attack_plan):
        try:
            c_address = to_checksum_address(self.args.contract_address)
            w_address = to_checksum_address(self.args.wallet_address)
            #payload = self.pack_payload_from_attack_plan(attack_plan)
            call_args = self.path_attack_payload(attack_plan.path
                                                 , int(str(attack_plan.initial_balance()))
                                                 , 0)
            #log.info("contract_address: %s", c_address)
            #log.info("call_args: %r", call_args)
            #contract=self.get_contract()
            #for i in range(3, 10):
            #    payload = [[123]*i]
            #    calldata = str(contract.encodeABI("multiswapd", payload))
            #    print(i, calldata[0:10])
            if 0:
                res = self.call_ll(from_address=w_address
                             , to_address=c_address
                             , calldata=attack_plan.get_calldata(self.args.deflationary))
                print("res", res)
                aa
                return True, None
            fn_name = self.args.deflationary and "multiswapd" or "multiswap"
            final_amount = self.call(function_name=fn_name
                      , from_address=w_address
                      , to_address=c_address
                      , call_args=call_args)
            return True, None, final_amount

        except ContractLogicError as err:
            txt = str(err)
            txt = txt.replace("Pancake: ", "")
            txt = txt.replace("BOFH:", "")
            txt = txt.replace("execution reverted:", "")
            txt = txt.strip()
            return False, txt, 0

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
    log_set_level(log_level.debug)
    log_register_sink(print)
    bofh = Attack(args)
    bofh()


if __name__ == '__main__':
    main()
