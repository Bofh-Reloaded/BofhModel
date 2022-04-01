from asyncio import get_event_loop
from functools import lru_cache

from bofh.utils.config_data import BOFH_START_TOKEN_ADDRESS, BOFH_CONTRACT_ADDRESS, BOFH_WALLET_ADDRESS, \
    BOFH_STATUS_DB_DSN, BOFH_WEB3_RPC_URL, BOFH_MAX_WORKERS
from bofh.utils.misc import progress_printer
from bofh.utils.web3 import Web3PoolExecutor, JSONRPCConnector, method_id, parse_data_parameters, \
    parse_string_return

from dataclasses import dataclass, fields, MISSING
from logging import getLogger, basicConfig, Filter

from bofh.model.database import ModelDB, StatusScopedCursor
from bofh.model.modules.graph import TheGraph
from bofh.model.modules.contract_calls import ContractCalling
from bofh.model.modules.status_preloaders import EntitiesPreloader
from bofh.model.modules.loggers import Loggers
from bofh_model_ext import log_level, log_register_sink, log_set_level



@dataclass
class Args:
    status_db_dsn: str = BOFH_STATUS_DB_DSN
    verbose: bool = False
    items_limit: int = 0
    web3_rpc_url: str = BOFH_WEB3_RPC_URL
    max_workers: int = BOFH_MAX_WORKERS
    chunk_size: int = 100
    start_token_address: str = BOFH_START_TOKEN_ADDRESS
    max_reserves_snapshot_age_secs: int = 7200
    force_reuse_reserves_snapshot: bool = False
    do_not_update_reserves_from_chain: bool = False
    contract_address: str = BOFH_CONTRACT_ADDRESS
    wallet_address: str = BOFH_WALLET_ADDRESS

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


__doc__=f"""Read token metadata like name, symbol decimals, etc, from Web3 RPC. Then update status db.

Usage: bofh.model.read_token_data [options]

Options:
  -h  --help
  -d, --status_db_dsn=<connection_str>      DB status dsn connection string. Default is {Args.status_db_dsn}
  -c, --web3_rpc_url=<url>                  Web3 RPC connection URL. Default is {Args.web3_rpc_url}
  -j, --max_workers=<n>                     number of RPC data ingest workers, default one per hardware thread. Default is {Args.max_workers}
  -v, --verbose                             debug output
  --chunk_size=<n>                          preloaded work chunk size per each worker Default is {Args.chunk_size}
  --start_token_address=<address>           on-chain address of start token. Default is {Args.start_token_address}
  --max_reserves_snapshot_age_secs=<s>      max age of usable LP reserves DB snapshot (refuses to preload from DB if older). Default is {Args.max_reserves_snapshot_age_secs}
  --force_reuse_reserves_snapshot           disregard --max_reserves_snapshot_age_secs (use for debug purposes, avoids download of reserves)       
  --do_not_update_reserves_from_chain       do not attempt to forward an existing reserves DB snapshot to the latest known block
  --contract_address=<address>              set contract counterpart address. Default is {Args.contract_address}
  --wallet_address=<address>                funding wallet address. Default is {Args.wallet_address}
"""


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


class Runner(TheGraph
             , EntitiesPreloader
             , ContractCalling
             ):
    log = getLogger(__name__)

    def __init__(self, args: Args):
        EntitiesPreloader.__init__(self)
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        self.ioloop = get_event_loop()
        ContractCalling.__init__(self, args=self.args)
        TheGraph.__init__(self, self.db)

    @lru_cache
    def tokens_requiring_fees_ctr(self):
        with self.db as curs:
            return curs.execute("SELECT COUNT(1) FROM tokens "
                                "WHERE NOT disabled AND "
                                " NOT is_stabletoken AND"
                                "      fees_ppm IS NULL ").get_int()

    def tokens_requiring_fees(self):
        with self.db as curs:
            for i in curs.execute("SELECT address FROM tokens "
                                  "WHERE NOT disabled AND "
                                  " NOT is_stabletoken AND"
                                  "      fees_ppm IS NULL ").get_all():
                yield i[0]

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

    def read_token_fees(self):
        tokens_requiring_fees_ctr = self.tokens_requiring_fees_ctr()
        if not tokens_requiring_fees_ctr:
            self.log.info("no tokens requiring fee discovery")
            return
        self.log.info("%r tokens require fee discovery. Preloading the knowledge graph...", tokens_requiring_fees_ctr)
        #from IPython import embed
        #embed()
        self.load(load_reserves=False)
        progress = progress_printer(tokens_requiring_fees_ctr
                                    , "fetching token fees {percent}% ({count} of {tot}"
                                      " eta={expected_secs:.0f}s at {rate:.0f} items/s) ..."
                                    , on_same_line=True)
        missing_ctr = 0
        for addr in list(self.tokens_requiring_fees()):
            t = self.graph.lookup_token(addr)
            paths = list(self.graph.find_paths_to_token(t))
            progress()
            return
            if not paths:
                missing_ctr+=1
        self.log.info("out of %u known tokens, %u have no known paths to cross them"
                      , self.graph.tokens_count()
                      , missing_ctr)

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
                              "while %r were found broken and marked as disabled"
                              , progress.total
                              , progress.updates
                              , progress.broken)
            finally:
                self.db.commit()
            executor.shutdown(wait=True)



def main():
    basicConfig(level="INFO")
    log_set_level(log_level.debug)
    log_register_sink(Loggers.model)
    args = Args.from_cmdline(__doc__)
    import coloredlogs
    coloredlogs.install(level="DEBUG", datefmt='%Y%m%d%H%M%S')
    if not getattr(args, "verbose", 0):
        # limit debug log output to bofh.* loggers
        filter = Filter(name="bofh")
        for h in getLogger().handlers:
            h.addFilter(filter)

    runner = Runner(args)
    runner.read_token_names()
    runner.read_token_fees()


if __name__ == '__main__':
    main()