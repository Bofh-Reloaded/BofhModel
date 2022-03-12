from asyncio import get_event_loop

from jsonrpc_base import ProtocolError

from bofh.utils.misc import progress_printer, optimal_cpu_threads
from bofh.utils.solidity import get_abi
from bofh.utils.web3 import Web3Connector, JSONRPCConnector, method_id, encode_uint, Web3PoolExecutor, \
    parse_data_address, parse_data_parameters

__doc__="""Start model runner.

Usage: bofh.model.download_uniswap_exchange [options] <exchange_name> <router_address> <fees_ppm>
Options:
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
from bofh.model.modules.status_preloaders import EntitiesPreloader


@dataclass
class Args:
    status_db_dsn: str = None
    verbose: bool = False
    web3_rpc_url: str = None
    max_workers: int = 0
    exchange_name: str = None
    router_address: str = None
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
            , router_address=args["<router_address>"]
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


class Runner(TheGraph, ContractCalling, EntitiesPreloader):
    log = getLogger(__name__)

    def __init__(self, args: Args):
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        TheGraph.__init__(self, self.db)
        ContractCalling.__init__(self, self.args)
        EntitiesPreloader.__init__(self)
        self.pools_cache = set()

    def preload_existing_from_db(self):
        self.preload_exchanges()
        self.preload_tokens()
        self.preload_pools()
        exc = None
        with self.db as curs:
            for a in curs.list_exchanges():
                router_address = a[1]
                if router_address == self.args.router_address:
                    exc = self.graph.add_exchange(*a)
                    continue
            if not exc:
                return
            self.log.info("preloading existing tokens/pools for this exchange...")
            sql = curs.TOKENS_SELECT_TUPLE + "WHERE " \
                  "id IN (SELECT token0_id FROM pools WHERE exchange_id = ?) OR " \
                  "id IN (SELECT token1_id FROM pools WHERE exchange_id = ?)"
            for args in curs.execute(sql, (exc.tag, exc.tag)).get_all():
                self.graph.add_token(*args)

            for addr in curs.execute("SELECT address FROM pools WHERE exchange_id = ?", (exc.tag,)).get_all():
                self.pools_cache.add(addr)
            self.log.info("%u tokens preloaded from db", len(self.graph.tokens_count()))
            self.log.info("%u pools preloaded from db", len(self.pools_cache))

    def add_unknown_token(self, addr):
        with self.db as curs:
            tag = curs.add_token(addr)
            return self.graph.add_token(tag, addr, "", "", 18, False)

    def __call__(self):
        self.graph.set_fetch_token_addr_cb(self.add_unknown_token)
        class PoolFailed(RuntimeError): pass
        with self.db as curs:
            exchange_id = curs.add_exchange(self.args.router_address, self.args.exchange_name, self.args.fees_ppm, ignore_duplicates=True)
            self.log.info("reaching out to router at address %s", self.args.router_address)
            router = self.w3.eth.contract(address=self.args.router_address, abi=get_abi("IGenericRouter"))

            factory_addr = router.functions.factory().call()
            self.log.info("reaching out to factory at address %s", factory_addr)
            factory = self.w3.eth.contract(address=factory_addr, abi=get_abi("IGenericFactory"))
            pairs_nr = factory.functions.allPairsLength().call()
            self.log.info("according to factory, %r pairs exist", pairs_nr)

            with progress_printer(pairs_nr, "downloading pairs {percent}% ({count} of {tot}"
                                            " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                            , on_same_line=True) as progress:
                with Web3PoolExecutor(
                        connection_uri=self.args.web3_rpc_url
                        , max_workers=self.args.max_workers) as executor:
                    def sequence():
                        for i in range(pairs_nr):
                            yield factory_addr, i, False
                    for res in executor.map(do_work, sequence(), chunksize=100):
                        try:
                            if progress():
                                self.db.commit()
                            if not res:
                                # the call failed
                                continue
                            pool_id, pool_addr, token0, token1, reserve0, reserve1, blocknr = res
                            if pool_addr in self.pools_cache:
                                # pool already loaded
                                continue
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
                                                , token1_id=tids[1])
                        except PoolFailed as err:
                            self.log.error("giving up un pool %s due to error", err)
                            pass


def main():
    basicConfig(level="INFO")
    args = Args.from_cmdline(__doc__)
    runner = Runner(args)
    runner.preload_existing_from_db()
    runner()


if __name__ == '__main__':
    main()