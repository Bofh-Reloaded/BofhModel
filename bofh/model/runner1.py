"""Start model runner.

Usage: bofh.model.runner1 [options]

Options:
  -h  --help
  -d, --dsn=<connection_str>    DB dsn connection string [default: sqlite3://status.db]
  -c, --connection_url=<url>    Web3 RPC connection URL [default: ws://localhost:8546]
  -n <n>                        number of pools to query before exit (benchmark mode)
  -j <n>                        number of RPC data ingest workers, default one per hardware thread. Only used during initialization phase
  -v, --verbose                 debug output
  --chunk_size=<n>              preloaded work chunk size per each worker [default: 100]
"""
from dataclasses import dataclass
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB
from bofh_model_ext import TheGraph


@dataclass
class Args:
    status_db_dsn: str = None
    verbose: bool = False
    pools_limit: int = 0
    web3_rpc_url: str = None
    max_workers: int = 0
    chunk_size: int = 0

    @staticmethod
    def default(arg, d):
        if arg: return arg
        return d

    @classmethod
    def from_cmdline(cls, docstr):
        from docopt import docopt
        args = docopt(docstr)
        return cls(
            status_db_dsn = args["--dsn"]
            , verbose=bool(cls.default(args["--verbose"], 0))
            , pools_limit=int(cls.default(args["-n"], 0))
            , web3_rpc_url=cls.default(args["--connection_url"], 0)
            , max_workers=int(cls.default(args["-j"], 0))
            , chunk_size=int(cls.default(args["--chunk_size"], 100))
        )


class Runner:
    log = getLogger(__name__)

    def __init__(self, args: Args):
        self.graph = TheGraph()
        self.args = args
        self.db = ModelDB(self.args.status_db_dsn)
        self.db.open_and_priming()
        self.exchanges_map = dict()
        self.tokens_map = dict()
        self.pools_map = dict()

    def preload_exchanges(self):
        with self.db as curs:
            for id, *args in curs.list_exchanges():
                addr = self.graph.add_exchange(*args)
                assert addr is not None
                self.exchanges_map[id] = addr

    def preload_tokens(self):
        with self.db as curs:
            for id, *args, is_stabletoken in curs.list_tokens():
                addr = self.graph.add_token(*args, bool(is_stabletoken))
                if addr is None:
                    raise RuntimeError("integrity error: token address is already not of a token: id=%r, %r" % (id, args))
                self.tokens_map[id] = addr

    skip = 0
    tot = 0
    def preload_pools(self):

        with self.db as curs:
            for id, address, exchange_id, token0_id, token1_id in curs.list_pools():
                addr = self.graph.add_swap_pair(address, self.tokens_map[token0_id], self.tokens_map[token1_id])
                self.tot += 1
                if addr is None:
                    self.skip += 1
                    print ("integrity error: token address is already not of a pool: id=%r, %r -- skip %r over %r" % (id,address, self.skip, self.tot))
                    #raise RuntimeError("integrity error: token address is already not of a pool: id=%r, %r" % (id,address))
                #self.pools_map[id] = addr

    """
    def list_pools_db(self):
        if self.args.verbose:
            self.log.info("loading pool data from %s", self.args.status_db_dsn)
        with self.db as curs:
            for k, v in pools.items():
                for ex_name, exchange in v.items():
                    for pool in exchange["pools"]:
                        if i and (i % 5000) == 0:
                            if self.args.verbose:
                                self.log.info("fetch %r pools ...", i)
                        yield pool["address"]
                        i += 1
                        if self.args.pools_limit and i >= self.args.pools_limit:
                            self.log.info("stopping at pool #%d, before the end", self.args.pools_limit)
                            return

    def priming_status_from_blockchain(self):
        with Web3PoolExecutor(connection_uri=self.args.web3_rpc_url, max_workers=self.args.max_workers) as executor:
            self.log.info("Preloading pool %s status from %s"
                     "\n\t- using %d workers"
                     "\n\t- each with a %d preload queue"
                     , Args.default(self.args.pools_limit, "unbound")
                     , Args.default(self.args.web3_rpc_url, "default")
                     , executor.max_workers
                     , self.args.chunk_size
                     )
            list(executor.map(getReserves, pools_iterator(), chunksize=chunk_size))
            executor.shutdown(wait=True)
            total = how_many_pools
        exec_time = time.process_time()
        return load_time - t, exec_time - load_time, total

    def load_pools(self, filename, conn_url, how_many_pools, max_workers, verbose, chunk_size):
        log = getLogger(__name__)
        opener = open
        if filename.endswith(".gz"):
            import gzip
            opener = gzip.open

        if verbose:
            log.info("loading pool data from %s", filename)
        with opener('bsc_pools.data') as pool_data:
            pools = json.load(pool_data)

        def pools_iterator(): # really super lazy
            i = 0
            for k, v in pools.items():
                for ex_name, exchange in v.items():
                    for pool in exchange["pools"]:
                        if i and (i % 5000) == 0:
                            if verbose:
                                log.info("fetch %r pools ...", i)
                        yield pool["address"]
                        i += 1
                        if i >= how_many_pools:
                            return

        with Web3PoolExecutor(connection_uri=conn_url, max_workers=max_workers) as executor:
            log.info("performing benchmark:"
                     "\n\t- %r pool getReserve requests"
                     "\n\t- on Web3 servant at %s"
                     "\n\t- using %d workers"
                     "\n\t- each with a %d preload queue"
                      , default(how_many_pools, "unbound")
                      , default(conn_url, "default")
                      , executor._max_workers
                      , chunk_size
                      )
            list(executor.map(getReserves, pools_iterator(), chunksize=chunk_size))
            executor.shutdown(wait=True)
            total = how_many_pools
        exec_time = time.process_time()
        return load_time - t, exec_time - load_time, total
    """


def main():
    basicConfig(level="INFO")
    runner = Runner(Args.from_cmdline(__doc__))
    runner.preload_exchanges()
    runner.preload_tokens()
    runner.preload_pools()


if __name__ == '__main__':
    main()