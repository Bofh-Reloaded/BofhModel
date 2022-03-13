from bofh.utils.misc import optimal_cpu_threads
from bofh.utils.web3 import Web3Connector

__doc__="""Update pool reserves.

Usage: bofh.model.update_pool_reserves [options]

options:
  -h  --help
  -d, --dsn=<connection_str>            DB dsn connection string [default: sqlite3://status.db]
  -c, --connection_url=<url>            Web3 RPC connection URL [default: %s]
  -j <n>                                number of RPC data ingest workers, default one per hardware thread [default: %u]
  --chunk_size=<n>                      preloaded work chunk size per each worker [default: 100]
  -v, --verbose                         debug output
""" % (Web3Connector.DEFAULT_URI_WSRPC, optimal_cpu_threads())

from dataclasses import dataclass
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB, StatusScopedCursor
from bofh.model.modules.graph import TheGraph
from bofh.model.modules.contract_calls import ContractCalling
from bofh.model.modules.status_preloaders import EntitiesPreloader


@dataclass
class Args:
    status_db_dsn: str = None
    verbose: bool = False
    web3_rpc_url: str = None
    max_workers: int = 0
    chunk_size: int = 0

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
            , max_workers=int(cls.default(args["-j"], 0))
            , chunk_size=int(cls.default(args["--chunk_size"], 100))
        )


class Runner(TheGraph, ContractCalling, EntitiesPreloader):
    log = getLogger(__name__)

    def __init__(self, args: Args):
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        TheGraph.__init__(self, self.db)
        ContractCalling.__init__(self, self.args)
        EntitiesPreloader.__init__(self)

    def __call__(self):
        self.preload_exchanges()
        self.preload_pools()
        self.download_reserves_snapshot_from_web3()


def main():
    basicConfig(level="INFO")
    args = Args.from_cmdline(__doc__)
    runner = Runner(args)
    runner()


if __name__ == '__main__':
    main()