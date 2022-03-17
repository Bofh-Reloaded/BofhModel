from asyncio import get_event_loop

from eth_utils import to_checksum_address
from jsonrpc_base import ProtocolError

from bofh.utils.misc import progress_printer, optimal_cpu_threads
from bofh.utils.solidity import get_abi
from bofh.utils.web3 import Web3Connector, JSONRPCConnector, method_id, encode_uint, Web3PoolExecutor, \
    parse_data_address, parse_data_parameters

__doc__="""Start model runner.

Usage: bofh.model.download_exchange [options] <exchange_name> <factory_address> <fees_ppm>

options:
  -h  --help
  -d, --dsn=<connection_str>            DB dsn connection string [default: sqlite3://status.db]
  -c, --connection_url=<url>            Web3 RPC connection URL [default: %s]
  -j <n>                                number of RPC data ingest workers, default one per hardware thread [default: %u]
  -v, --verbose                         debug output
""" % (Web3Connector.DEFAULT_URI_WSRPC, optimal_cpu_threads())

from dataclasses import dataclass
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB, StatusScopedCursor
from bofh.model.modules.graph import TheGraph
from bofh.model.modules.contract_calls import ContractCalling

@dataclass
class Args:
    status_db_dsn: str = None
    verbose: bool = False
    web3_rpc_url: str = None
    max_workers: int = 0
    exchange_name: str = None
    factory_address: str = None
    fees_ppm: int = 0

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
            , exchange_name=args["<exchange_name>"]
            , factory_address=args["<factory_address>"]
            , fees_ppm=int(args["<fees_ppm>"])
        )


class RPCtasks:
    def __init__(self):
        self.exe = JSONRPCConnector.get_connection()
        self.ioloop = get_event_loop()
        self.mid_getPair = method_id("allPairs(uint256)")
        self.mid_t0 = method_id("token0()")
        self.mid_t1 = method_id("token1()")
        self.mid_getReserves = method_id("getReserves()")

    def getPair(self, factory_address, pair_idx): # returns pool_addr
        data = self.mid_getPair+encode_uint(pair_idx)
        fut = self.exe.eth_call({"to": factory_address, "data": data}, "latest")
        res = self.ioloop.run_until_complete(fut)
        return parse_data_address(res)

    def getTokens(self, pool_addr):  # returns pool_id, pool_addr, token0addr, token1addr
        fut = self.exe.eth_call({"to": pool_addr, "data": self.mid_t0}, "latest")
        res0 = self.ioloop.run_until_complete(fut)
        fut = self.exe.eth_call({"to": pool_addr, "data": self.mid_t1}, "latest")
        res1 = self.ioloop.run_until_complete(fut)
        return pool_addr, parse_data_address(res0), parse_data_address(res1)

    def getReserves(self, pool_id, pool_addr):  # returns pool_id, reserve0, reserve1, latestBlockNr
        fut = self.exe.eth_call({"to": pool_addr, "data": self.mid_getReserves}, "latest")
        res3 = self.ioloop.run_until_complete(fut)
        reserve0, reserve1, lastblockN = parse_data_parameters(res3)
        return pool_id, reserve0, reserve1, lastblockN

    @classmethod
    def instance(cls):
        try:
            return cls._instance
        except AttributeError:
            cls._instance = cls()
        return cls._instance


def do_work(a):
    factory_address, pool_id, get_reserves = a
    for i in range(4):  # try multiple times
        try:
            rpc = RPCtasks.instance()
            pool_addr = rpc.getPair(factory_address, pool_id)
            _, token0, token1 = rpc.getTokens(pool_addr)
            if get_reserves:
                _, reserve0, reserve1, blocknr = rpc.getReserves(pool_id, pool_addr)
            else:
                reserve0, reserve1, blocknr = None, None, None
            return pool_id, pool_addr, token0, token1, reserve0, reserve1, blocknr
        except ProtocolError:
            pass


class Runner(TheGraph, ContractCalling):
    log = getLogger(__name__)

    def __init__(self, args: Args):
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        TheGraph.__init__(self, self.db)
        ContractCalling.__init__(self, self.args)

    def add_unknown_token(self, addr):
        with self.db as curs:
            tag = curs.add_token(addr, ignore_duplicates=True)
            return self.graph.add_token(tag, addr, "", "", 18, False, 0)

    def __call__(self):
        self.graph.set_fetch_token_addr_cb(self.add_unknown_token)
        class PoolFailed(RuntimeError): pass
        with self.db as curs:
            exchange_id = curs.add_exchange(self.args.factory_address, self.args.exchange_name, self.args.fees_ppm, ignore_duplicates=True)
            factory_addr = to_checksum_address(self.args.factory_address)
            self.log.info("reaching out to factory at address %s", factory_addr)
            factory = self.w3.eth.contract(address=factory_addr, abi=get_abi("IGenericFactory"))
            pairs_nr = factory.functions.allPairsLength().call()
            self.log.info("according to factory, %r pairs exist", pairs_nr)
            start_nr = curs.get_exchange_pools_count(exchange_id)
            self.log.info("%r pairs are already in our knowledge graph", start_nr)
            dl_count = pairs_nr - start_nr
            if dl_count == 0:
                self.log.info("no new pools to download")
                return

            with progress_printer(dl_count, "downloading pairs {percent}% ({count} of {tot}"
                                            " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                            , on_same_line=True) as progress:
                with Web3PoolExecutor(
                        connection_uri=self.args.web3_rpc_url
                        , max_workers=self.args.max_workers) as executor:
                    def sequence():
                        for i in range(start_nr, pairs_nr):
                            yield factory_addr, i, False
                    for res in executor.map(do_work, sequence(), chunksize=100):
                        try:
                            if progress():
                                self.db.commit()
                            if not res:
                                # the call failed
                                continue
                            pool_id, pool_addr, token0, token1, reserve0, reserve1, blocknr = res
                            if token0 == token1:
                                self.log.warning("pool %s appears to be circular on token %s: skipped", pool_addr,
                                                 token0)
                                continue
                            tids = []
                            for addr in token0, token1:
                                tok = self.graph.lookup_token(addr)
                                if tok is None:
                                    raise PoolFailed(pool_addr)
                                tids.append(tok.tag)
                            curs.add_swap(address=pool_addr
                                                , exchange_id=exchange_id
                                                , token0_id=tids[0]
                                                , token1_id=tids[1]
                                                , ignore_duplicates=True)
                        except PoolFailed as err:
                            self.log.error("giving up un pool %s due to error", err)
                            pass


def main():
    basicConfig(level="INFO")
    args = Args.from_cmdline(__doc__)
    runner = Runner(args)
    #runner.preload_existing_from_db()
    runner()


if __name__ == '__main__':
    main()