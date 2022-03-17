from tabulate import tabulate

from bofh.utils.web3 import Web3Connector

__doc__=f"""Start model runner.

Usage: bofh.model.manage_exchanges [options]

options:
  -h  --help
  -d, --dsn=<connection_str>            DB dsn connection string [default: sqlite3://status.db]
  -c, --connection_url=<url>            Web3 RPC connection URL [default: {Web3Connector.DEFAULT_URI_WSRPC}]
  --list                                list current exchanges
  --format=<format>                     table, line [default: table]
  -v, --verbose                         debug output
"""

from dataclasses import dataclass
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB, StatusScopedCursor

@dataclass
class Args:
    status_db_dsn: str = None
    verbose: bool = False
    web3_rpc_url: str = None
    list: bool = False
    format: str = "table"

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
            , web3_rpc_url=cls.default(args["--connection_url"], 0)
            , list=bool(args.get("--list"))
            , format=str(args.get("--format"))
        )


class Runner:
    log = getLogger(__name__)

    def __init__(self, args: Args):
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()

    def __call__(self):
        self.list()

    def list(self):
        headers = ["name", "factory", "fees"]
        data=[]
        with self.db as curs:
            for id,factory,name,fees_ppm in curs.list_exchanges():
                data.append([name, factory, fees_ppm])
        if self.args.format == "table":
            print(tabulate(data, headers=headers, tablefmt="orgtbl"))
        else:
            for i in data:
                print(*i)


def main():
    basicConfig(level="INFO")
    args = Args.from_cmdline(__doc__)
    runner = Runner(args)
    runner()


if __name__ == '__main__':
    main()