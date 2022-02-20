from threading import Lock
from time import strftime, gmtime

from eth_utils import to_checksum_address
from tabulate import tabulate

from bofh.model.modules.cached_entities import CachedEntities
from bofh.model.modules.constants import ENV_SWAP_CONTRACT_ADDRESS, ENV_BOFH_WALLET_ADDRESS, \
    ENV_BOFH_WALLET_PASSWD, START_TOKEN
from bofh.model.modules.contract_calls import ContractCalling
from bofh.model.modules.loggers import Loggers
from bofh.utils.web3 import Web3Connector, JSONRPCConnector

from dataclasses import dataclass, fields, MISSING
from logging import basicConfig, Filter, getLogger

from bofh.model.database import ModelDB, StatusScopedCursor, Intervention


@dataclass
class Args:
    status_db_dsn: str = "sqlite3://status.db"
    verbose: bool = False
    web3_rpc_url: str = None
    contract_address: str = ENV_SWAP_CONTRACT_ADDRESS
    wallet_address: str = ENV_BOFH_WALLET_ADDRESS
    wallet_password: str = ENV_BOFH_WALLET_PASSWD
    logfile: str = None
    loglevel_database: str = "INFO"
    loglevel_contract_activation: str = "INFO"
    token: str = START_TOKEN
    status: bool = True
    increase_funding: int = None
    reclaim: bool = True
    dry_run: bool = False
    weis: bool = False
    yes: bool = False

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


class Funding(ContractCalling, CachedEntities):
    def __init__(self, args: Args):
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        self.args.sync_db(self.db)
        CachedEntities.__init__(self, self.db)

    def __call__(self, *args, **kwargs):
        try:
            if self.args.increase_funding:
                self.increase_funding(self.args.increase_funding)
            elif self.args.reclaim:
                self.reclaim()
            elif self.args.status:
                self.status()
            else:
                log.error("please specify a command: --status, --increase_funding, --reclaim")
        except ManagedAbort as err:
            log.error(str(err))

    def increase_funding(self, amount):
        assert amount > 0
        token = self.get_token(self.args.token)
        c_address = to_checksum_address(self.args.contract_address)
        w_address = to_checksum_address(self.args.wallet_address)
        c_balance = self.getTokenBalance(c_address, token)
        w_balance = self.getTokenBalance(w_address, token)
        hc = self.amount_hr(c_balance, token)
        hw = self.amount_hr(w_balance, token)
        log.info(f"wallet   {w_address} has {hw} {token.get_symbol()}")
        log.info(f"contract {c_address} has {hc} {token.get_symbol()}")
        hr = self.amount_hr(amount, token)
        if w_balance < amount:
            log.error(f"wallet balance of {hw} {token.get_symbol()} ({w_balance}) "
                      f"is not enough to cover trasfer of {hr} ({amount}) {token.get_symbol()}")
            raise ManagedAbort("not enough wallet funds")
        log.debug("performing preflight check of transfer transaction...")
        calls = [
            dict(function_name="approve"
                  , from_address=w_address
                  , to_address=token.address
                  , abi="IGenericFungibleToken"
                  , call_args=(c_address, amount))
            ,
            dict(function_name="adoptAllowance"
                  , from_address=w_address
                  , to_address=c_address)
        ]
        for c in calls:
            self.call(**c)
        log.debug("preflight check passed")

        log.info("this transfer would move %0.4f%% of current wallet %s balance to the contract", (amount/w_balance)*100, token.get_symbol())
        prompt(self.args, f"Move {hr} ({amount}) {token.get_symbol()} from wallet to contract address at {c_address}?")
        log.info("unlocking wallet...")
        self.unlock_wallet(w_address, self.args.wallet_password)
        log.info(f"calling {token.address}.approve({c_address}, {amount}) ...")
        tx = self.transact(**calls[0])
        log.debug("transaction published at %s", tx.hex())
        log.info(f"calling {c_address}.adoptAllowance() ...")
        tx = self.transact(**calls[1])
        log.debug("transaction published at %s", tx.hex())
        log.info("transfer completed successfully :-)")

    def reclaim(self):
        pass

    def status(self):
        token = self.get_token(self.args.token)
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
        line = ["contract", address, ht_tok, token.get_symbol()]
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
        line = ["wallet", address, ht_tok, token.get_symbol()]
        if self.args.weis:
            line.append(token_balance)
        data.append(line)

        print(tabulate(data, headers=headers))

    def amount_hr(self, amount, token=None):
        if token is None:
            return "%0.4f" % (amount / (10**18))
        return "%0.4f" % token.fromWei(amount)


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
