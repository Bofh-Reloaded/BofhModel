from asyncio import get_event_loop
from functools import lru_cache
from bofh.utils.misc import progress_printer
from bofh.utils.web3 import Web3Connector, Web3PoolExecutor, JSONRPCConnector, method_id, parse_data_parameters, \
    parse_string_return

__doc__="""Read token metadata like name, symbol decimals, etc, from Web3 RPC. Then update status db.

Usage: bofh.model.read_token_data [options]

Options:
  -h  --help
  -d, --dsn=<connection_str>            DB dsn connection string [default: sqlite3://status.db]
  -c, --connection_url=<url>            Web3 RPC connection URL [default: %s]
  -n <n>                                limit number of items to load (benchmark mode)
  -j <n>                                number of RPC data ingest workers, default one per hardware thread. Only used during initialization phase
  -v, --verbose                         debug output
  --chunk_size=<n>                      preloaded work chunk size per each worker [default: 100]
""" % Web3Connector.DEFAULT_URI_WSRPC

from dataclasses import dataclass
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB, BasicScopedCursor


@dataclass
class Args:
    status_db_dsn: str = None
    verbose: bool = False
    items_limit: int = 0
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
            , items_limit=int(cls.default(args["-n"], 0))
            , web3_rpc_url=cls.default(args["--connection_url"], 0)
            , max_workers=int(cls.default(args["-j"], 0))
            , chunk_size=int(cls.default(args["--chunk_size"], 100))
        )


def read_token_data(token_address):
    try:
        exe = read_token_data.exe
        ioloop = read_token_data.ioloop
        mid_decimals, mid_name, mid_symbol = read_token_data.mid
    except AttributeError:
        exe = read_token_data.exe = JSONRPCConnector.get_connection()
        ioloop = read_token_data.ioloop = get_event_loop()
        read_token_data.mid = (method_id("decimals()"), method_id("name()"), method_id("symbol()"))
        mid_decimals, mid_name, mid_symbol = read_token_data.mid
    try:
        # read symbol
        fut = exe.eth_call({"to": token_address, "data": mid_symbol}, "latest")
        res_symbol = parse_string_return(ioloop.run_until_complete(fut)).decode("utf-8").strip()
        # read decimals
        fut = exe.eth_call({"to": token_address, "data": mid_decimals}, "latest")
        res_decimals = parse_data_parameters(ioloop.run_until_complete(fut), cast=lambda x: x[0])
        # read name
        fut = exe.eth_call({"to": token_address, "data": mid_name}, "latest")
        res_name = parse_string_return(ioloop.run_until_complete(fut)).decode("utf-8").strip()
        return True, token_address, res_name, res_symbol, res_decimals
    except:
        return False, token_address, None, None, None


class Runner:
    log = getLogger(__name__)

    def __init__(self, args: Args):
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=BasicScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        self.ioloop = get_event_loop()

    @lru_cache
    def tokens_requiring_update_ctr(self):
        with self.db as curs:
            return curs.execute("SELECT COUNT(1) FROM tokens "
                                "WHERE NOT disabled AND ("
                                "      symbol   IS NULL "
                                "   OR name     IS NULL "
                                "   OR decimals IS NULL )").get_int()

    def tokens_requiring_update(self):
        with self.db as curs:
            for i in curs.execute("SELECT address FROM tokens "
                                  "WHERE NOT disabled AND ("
                                  "      symbol   IS NULL "
                                  "   OR name     IS NULL "
                                  "   OR decimals IS NULL )").get_all():
                yield i[0]

    def read_token_names(self):
        self.log.info("fetching token names...")
        progress = progress_printer(self.tokens_requiring_update_ctr()
                                          , "fetching token data {percent}% ({count} of {tot}"
                                            " eta={expected_secs:.0f}s at {rate:.0f} items/s) ..."
                                          , on_same_line=True)
        progress.updates = 0
        progress.broken = 0
        progress.total = 0
        with Web3PoolExecutor(connection_uri=self.args.web3_rpc_url, max_workers=self.args.max_workers) as executor:
            self.log.info("fetching token data via Web3:"
                          "\n\t- %r requests"
                          "\n\t- on Web3 servant at %s"
                          "\n\t- using %d workers"
                          "\n\t- each with a %d preload queue"
                           , self.tokens_requiring_update_ctr()
                           , self.args.web3_rpc_url
                           , self.args.max_workers
                           , self.args.chunk_size
                           )
            tokens_requiring_update = list(self.tokens_requiring_update())  # Consolidate list in RAM, so that the DB
                                                                            # is unlocked (we are updating it later)
            curs = self.db.cursor()
            try:
                for success, token_addr, name, symbol, decimals in executor.map(read_token_data,
                                                                       tokens_requiring_update,
                                                                       chunksize=self.args.chunk_size):
                    progress.total += 1
                    if success:
                        curs.execute("UPDATE tokens SET name=?, symbol=?, decimals=? WHERE address = ?", (name, symbol, decimals, token_addr))
                        progress.updates += 1
                    else:
                        curs.execute("UPDATE tokens SET disabled=1 WHERE address  = ?", (token_addr, ))
                        progress.broken += 1
                        if self.args.verbose:
                            self.log.warning("token %s seems to be broken. marking it with disabled=1", token_addr)
                    if progress():
                        self.db.commit()
                    if self.args.items_limit and progress.total >= self.args.items_limit:
                        self.log.info("aborting batch after %r items, due to -n CLI parameter", self.args.items_limit)
                        break
                self.log.info("batch completed for a total of %r tokens."
                              " %r tokens correctly updated, "
                              "while %r were found broken and marked as disabled=1"
                              , progress.total
                              , progress.updates
                              , progress.broken)
            finally:
                self.db.commit()
            executor.shutdown(wait=True)



def main():
    basicConfig(level="INFO")
    runner = Runner(Args.from_cmdline(__doc__))
    runner.read_token_names()


if __name__ == '__main__':
    main()