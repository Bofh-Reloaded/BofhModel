from asyncio import get_event_loop
from collections import defaultdict
from functools import lru_cache
from time import time

from eth_utils import to_checksum_address
from web3.exceptions import ContractLogicError

from bofh.contract import SwapInspection
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

    def __sql_tokens_requiring_fee_detection(self, neighbour_token=None):
        if neighbour_token is None:
            neighbour_token = self.graph.get_start_token()
        assert neighbour_token is not None
        return f"""
        WHERE NOT disabled 
        AND fees_ppm IS NULL 
        AND fees_read_attempt = 0
        AND (
            id IN (SELECT token1_id FROM pools WHERE token0_id = {neighbour_token.tag}) 
            OR 
            id in (SELECT token0_id FROM pools WHERE token1_id = {neighbour_token.tag})
        )"""

    def preload(self):
        try:
            self.__preloaded
        except AttributeError:
            self.load(load_reserves=False)
            self.__preloaded = 1

    @lru_cache
    def tokens_requiring_fees_ctr(self):
        with self.db as curs:
            return curs.execute("SELECT COUNT(1) FROM tokens " +
                                self.__sql_tokens_requiring_fee_detection()).get_int()

    def tokens_requiring_fees(self):
        with self.db as curs:
            for i in curs.execute("SELECT id FROM tokens "
                                  + self.__sql_tokens_requiring_fee_detection()).get_all():
                yield i[0]

    @lru_cache
    def tokens_requiring_update_ctr(self):
        with self.db as curs:
            return curs.execute("SELECT COUNT(1) FROM tokens "
                                "WHERE NOT disabled AND ("
                                "      symbol   IS NULL "
                                "   OR name     IS NULL "
                                "   OR decimals IS NULL ) "
                                "AND NOT fees_read_attempt").get_int()

    def tokens_requiring_update(self):
        with self.db as curs:
            for i in curs.execute("SELECT address FROM tokens "
                                  "WHERE NOT disabled AND ("
                                  "      symbol   IS NULL "
                                  "   OR name     IS NULL "
                                  "   OR decimals IS NULL ) "
                                  "AND NOT fees_read_attempt").get_all():
                yield i[0]

    def read_token_fees(self):
        self.preload()
        self.error_map = defaultdict(lambda: 0)
        tokens_requiring_fees_ctr = self.tokens_requiring_fees_ctr()
        if not tokens_requiring_fees_ctr:
            self.log.info("no tokens requiring fee discovery")
            return
        self.log.info("%r tokens require fee discovery. Preloading the knowledge graph...", tokens_requiring_fees_ctr)
        progress = progress_printer(tokens_requiring_fees_ctr
                                    , "fetching token fees {percent}% ({count} of {tot} ({failed} failed)"
                                      " eta={expected_secs:.0f}s at {rate:.0f} items/s) ..."
                                    , on_same_line=True)
        failed = 0
        dataset = list(self.tokens_requiring_fees())
        with self.db as curs, open("report.txt", "w") as fd:
            for id in dataset:
                if progress(failed=failed):
                    self.db.commit()
                t = self.graph.lookup_token(id)
                curs.execute("UPDATE tokens SET fees_read_attempt = ? WHERE id = ?", (int(time()), t.tag,))
                paths = list(self.graph.find_paths_to_token(t))
                if not paths:
                    self.log.warning("unable to cross token %r (%s). marking it as non-crossable", t.tag, t.symbol)
                    failed+=1
                    continue
                ok, _, fee_or_err = self.__test_paths(fd, t, paths)
                if not ok:
                    error = max(set(fee_or_err), key=fee_or_err.count)
                    self.log.warning("Unable to operate any exchange against token %r (%s): %s"
                                     , t.tag, t.symbol, error)
                    failed+=1
                    continue
                fee = fee_or_err
                assert isinstance(fee, int)
                try:
                    if fee < 0:
                        # go gad on inflationary tokens
                        raise OverflowError
                    curs.execute("UPDATE tokens SET fees_ppm = ? WHERE id = ?", (fee, t.tag))
                except OverflowError:
                    # I have seen this happen: a token so broken it yields a crazy fee that won't fit
                    # in an SQLite INT. Let's just mark it as bad and move on.
                    failed += 1
                    continue
        self.log.info("out of %u known tokens, %u have no known paths to cross them"
                      , self.graph.tokens_count()
                      , failed)
        print(self.error_map)
        self.log.info("error stats:")
        for k, v in self.error_map.items():
            print(f" - {k} --> {v} occurrences")

    def __test_paths(self, fd, token, paths):
        start_token = self.graph.lookup_token(self.args.start_token_address)
        if not start_token:
            raise RuntimeError("unable to lookup token entity: %r" % self.args.start_token_address)
        address = self.args.contract_address
        token_balance = self.getTokenBalance(address, start_token)
        if not token_balance:
            raise RuntimeError("test contract %s has no token funding" % address)
        errors = list()
        for path in paths:
            ok, err, data = self.__inspect_path(path, initial_amount=10**18)
            if ok:
                assert (data
                        and isinstance(data, list)
                        and isinstance(data[-1], SwapInspection)
                        and data[-1].tokenOut == str(token.address)
                        )
                si = data[-1]
                return True, token, self.__calc_token_trasfer_fee(transferredAmountOut=si.transferredAmountOut
                                                                  , measuredAmountOut=si.measuredAmountOut)
            else:
                self.error_map[err] += 1
                errors.append(err)
        return False, token, errors

    def __inspect_path(self, path, initial_amount):
        try:
            c_address = to_checksum_address(self.args.contract_address)
            w_address = to_checksum_address(self.args.wallet_address)
            call_args = SwapInspection.inspection_calldata(path=path, initial_amount=initial_amount)
            out = self.call(function_name="swapinspect"
                      , from_address=w_address
                      , to_address=c_address
                      , call_args=call_args)
            return True, None, SwapInspection.from_output(out)
        except ContractLogicError as err:
            txt = str(err)
            txt = txt.replace("Pancake: ", "")
            txt = txt.replace("BOFH:", "")
            txt = txt.replace("execution reverted:", "")
            txt = txt.strip()
            return False, txt, 0

    def __calc_token_trasfer_fee(self, transferredAmountOut, measuredAmountOut):
        assert isinstance(transferredAmountOut, int)
        assert isinstance(measuredAmountOut, int)
        missing = transferredAmountOut-measuredAmountOut
        return int(1000000 * missing / transferredAmountOut)


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