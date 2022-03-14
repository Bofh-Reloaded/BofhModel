from eth_utils import to_checksum_address
from tabulate import tabulate
from bofh.model.modules.graph import TheGraph
from bofh.model.modules.contract_calls import ContractCalling
from dataclasses import dataclass, fields, MISSING
from logging import basicConfig, Filter, getLogger

from bofh.model.database import ModelDB, StatusScopedCursor
from bofh.utils.config_data import BOFH_STATUS_DB_DSN, BOFH_WEB3_RPC_URL, BOFH_CONTRACT_ADDRESS, BOFH_WALLET_ADDRESS, \
    BOFH_WALLET_PASSWD, BOFH_START_TOKEN_ADDRESS


@dataclass
class Args:
    status_db_dsn: str = BOFH_STATUS_DB_DSN
    verbose: bool = False
    web3_rpc_url: str = BOFH_WEB3_RPC_URL
    contract_address: str = BOFH_CONTRACT_ADDRESS
    wallet_address: str = BOFH_WALLET_ADDRESS
    wallet_password: str = BOFH_WALLET_PASSWD
    logfile: str = None
    loglevel_database: str = "INFO"
    loglevel_contract_activation: str = "INFO"
    token: str = BOFH_START_TOKEN_ADDRESS
    status: bool = True
    increase_funding: int = None
    reclaim: bool = True
    selfdestruct: bool = True
    dry_run: bool = False
    weis: bool = False
    yes: bool = False

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


__doc__ = f"""Manage on-contract token funding.

Usage: bofh.model.funding [options]

Options:
  -h  --help
  -d, --status_db_dsn=<connection_str>    DB status dsn connection string. Default is {Args.status_db_dsn}
  -c, --web3_rpc_url=<url>                Web3 RPC connection URL. Default is {Args.web3_rpc_url}
  -v, --verbose                           debug output
  --wallet_address=<address>              funding wallet address. Default from BOFH_WALLET_ADDRESS envvar
  --wallet_password=<pass>                funding wallet address. Default from BOFH_WALLET_PASSWD envvar
  --contract_address=<address>            set contract address. Default from BOFH_CONTRACT_ADDRESS envvar

  --token=<address>                       operate with specified token. Default is {Args.token}
  --status                                print current on-chain status of contract and wallet funding (default option)
  --weis                                  Also print amounts in wei units
  
  --increase_funding=<wei>                transfer an amount of --token from the wallet to the --contract_address
  --reclaim                               retrieve 100% of the --contract_address token funds to contract admin address
  --selfdestruct                          calls self-destruct on the contract. All funds are returned to the admin address
  -n, --dry_run                           siluate transfer transaction with no actual execution
  -y, --yes                               do not ask for confirmation

Logging options:  
  --logfile=<file>                        log to file
  --loglevel_runner=<level>               set subsystem loglevel. Default is INFO
  --loglevel_database=<level>             set subsystem loglevel. Default is INFO
  --loglevel_model=<level>                set subsystem loglevel. Default is INFO
  --loglevel_constant_prediction=<level>  set subsystem loglevel. Default is INFO
"""

log = getLogger("bofh.model.funding")


class ManagedAbort(RuntimeError): pass


def prompt(args: Args, msg):
    if not args.yes:
        print("%s [y/N]" % msg)
        yes = {'yes', 'y', 'ye'}

        choice = input().lower()
        if choice in yes:
            return True
        raise ManagedAbort("Bailing out due to user choice")


class Funding(ContractCalling, TheGraph):
    def __init__(self, args: Args):
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        ContractCalling.__init__(self, self.args)
        TheGraph.__init__(self, self.db)

    def __call__(self, *args, **kwargs):
        try:
            if self.args.increase_funding:
                self.increase_funding(self.args.increase_funding)
            elif self.args.reclaim:
                self.reclaim()
            elif self.args.selfdestruct:
                self.selfdestruct()
            elif self.args.status:
                self.status()
            else:
                log.error("please specify a command: --status, --increase_funding, --reclaim")
        except ManagedAbort as err:
            log.error(str(err))

    def increase_funding(self, amount):
        assert amount > 0
        token = self.graph.lookup_token(self.args.token)
        c_address = to_checksum_address(self.args.contract_address)
        w_address = to_checksum_address(self.args.wallet_address)
        c_balance = self.getTokenBalance(c_address, token)
        w_balance = self.getTokenBalance(w_address, token)
        hc = self.amount_hr(c_balance, token)
        hw = self.amount_hr(w_balance, token)
        log.info(f"wallet   {w_address} has {hw} {token.symbol}")
        log.info(f"contract {c_address} has {hc} {token.symbol}")
        hr = self.amount_hr(amount, token)
        if w_balance < amount:
            log.error(f"wallet balance of {hw} {token.symbol} ({w_balance}) "
                      f"is not enough to cover trasfer of {hr} ({amount}) {token.symbol}")
            raise ManagedAbort("not enough wallet funds")
        log.debug("performing preflight check of transfer transaction...")
        log.info("unlocking wallet...")
        self.unlock_wallet(w_address, self.args.wallet_password)
        calls = [
            dict(function_name="approve"
                  , from_address=w_address
                  , to_address=token.address
                  , abi="IGenericFungibleToken"
                  , call_args=(c_address, amount))
            , dict(function_name="adoptAllowance"
                  , from_address=w_address
                  , to_address=c_address)
        ]
        for c in calls:
            print(self.call(**c))
        log.debug("preflight check passed")

        log.info("this transfer would move %0.4f%% of current wallet %s balance to the contract", (amount/w_balance)*100, token.symbol)
        prompt(self.args, f"Move {hr} ({amount}) {token.symbol} from wallet to contract address at {c_address}?")
        log.info("unlocking wallet...")
        self.unlock_wallet(w_address, self.args.wallet_password)
        log.info(f"calling {token.address}.approve({c_address}, {amount}) ...")
        receipt = self.transact_and_wait(**calls[0])
        log.debug("transaction receipt received. tx hash = %s", receipt["blockHash"].hex())
        log.info(f"calling {c_address}.adoptAllowance() ...")
        receipt = self.transact_and_wait(**calls[1])
        log.debug("transaction receipt received. tx hash = %s", receipt["blockHash"].hex())
        log.info("transfer completed successfully :-)")

    def reclaim(self):
        token = self.graph.lookup_token(self.args.token)
        c_address = to_checksum_address(self.args.contract_address)
        token_balance = self.getTokenBalance(c_address, token)
        ht_tok = self.amount_hr(token_balance, token)
        w_address = to_checksum_address(self.args.wallet_address)
        weis = ""
        if self.args.weis:
            weis = f" ({token_balance} weis)"
        log.info(f"contract {c_address} is currently storing {ht_tok} {token.symbol}{weis}")
        prompt(self.args, f"Reclaim {ht_tok} {token.symbol}{weis}? "
                          f"(Funds will be transferred to the contract's admin address)")
        self.unlock_wallet(w_address, self.args.wallet_password)
        receipt = self.transact_and_wait(function_name="withdrawFunds"
                                         , from_address=w_address
                                         , to_address=c_address)
        log.debug("transaction receipt received. tx hash = %s", receipt["blockHash"].hex())

    def status(self):
        token = self.graph.lookup_token(self.args.token)
        address = self.args.contract_address
        coin_balance = self.getCoinBalance(address)
        token_balance = self.getTokenBalance(address, token)
        hr_coin = self.amount_hr(coin_balance)
        ht_tok = self.amount_hr(token_balance, token)
        data = []
        headers = ["", "addr", "amount", "asset"]
        if self.args.weis:
            headers.append("weis")

        line = ["contract", address, hr_coin, self.coin_name]
        if self.args.weis:
            line.append(coin_balance)
        data.append(line)
        line = ["contract", address, ht_tok, token.symbol]
        if self.args.weis:
            line.append(token_balance)
        data.append(line)

        address = self.args.wallet_address
        coin_balance = self.getCoinBalance(address)
        token_balance = self.getTokenBalance(address, token)
        hr_coin = self.amount_hr(coin_balance)
        ht_tok = self.amount_hr(token_balance, token)

        line = ["wallet", address, hr_coin, self.coin_name]
        if self.args.weis:
            line.append(coin_balance)
        data.append(line)
        line = ["wallet", address, ht_tok, token.symbol]
        if self.args.weis:
            line.append(token_balance)
        data.append(line)

        print(tabulate(data, headers=headers))

    def selfdestruct(self):
        token = self.graph.lookup_token(self.args.token)
        c_address = to_checksum_address(self.args.contract_address)
        token_balance = self.getTokenBalance(c_address, token)
        ht_tok = self.amount_hr(token_balance, token)
        w_address = to_checksum_address(self.args.wallet_address)
        weis = ""
        if self.args.weis:
            weis = f" ({token_balance} weis)"
        log.info(f"contract {c_address} is currently storing {ht_tok} {token.symbol}{weis}")
        prompt(self.args, f"Call selfdestruct on contract {c_address}? "
                          f"(Funds will be transferred to the contract's admin address)")
        self.unlock_wallet(w_address, self.args.wallet_password)
        receipt = self.transact_and_wait(function_name="kill"
                                         , from_address=w_address
                                         , to_address=c_address)
        log.debug("transaction receipt received. tx hash = %s", receipt["blockHash"].hex())

    def amount_hr(self, amount, token=None):
        if token is None:
            return "%0.4f" % (amount / (10**18))
        return "%0.4f" % token.fromWei(amount)

    @property
    def coin_name(self):
        return "BNB"



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
    bofh = Funding(args)
    bofh()


if __name__ == '__main__':
    main()
