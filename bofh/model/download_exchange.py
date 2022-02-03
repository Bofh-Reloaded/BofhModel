from asyncio import get_event_loop
from concurrent.futures import Future

from jsonrpc_base import ProtocolError

from bofh.utils.misc import progress_printer, optimal_cpu_threads
from bofh.utils.solidity import get_abi
from bofh.utils.web3 import Web3Connector, JSONRPCConnector, method_id, encode_uint, Web3PoolExecutor, \
    parse_data_address, parse_data_parameters

__doc__="""Start model runner.

Usage: bofh.model.download_uniswap_exchange [options] <exchange_name> <router_address>

Options:
  -h  --help
  -d, --dsn=<connection_str>            DB dsn connection string [default: sqlite3://status.db]
  -c, --connection_url=<url>            Web3 RPC connection URL [default: %s]
  --reserves                            download/refresh reserves
  -j <n>                                number of RPC data ingest workers, default one per hardware thread [default: %u]
  -v, --verbose                         debug output
""" % (Web3Connector.DEFAULT_URI_WSRPC, optimal_cpu_threads())

from dataclasses import dataclass
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB, StatusScopedCursor



@dataclass
class Args:
    status_db_dsn: str = None
    verbose: bool = False
    web3_rpc_url: str = None
    reserves: bool = False
    max_workers: int = 0
    exchange_name: str = None
    router_address: str = None

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
            , reserves=bool(cls.default(args["--reserves"], 0))
            , max_workers=int(cls.default(args["-j"], 0))
            , exchange_name=args["<exchange_name>"]
            , router_address=args["<router_address>"]
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
                reserve0, reserve1, blocknr = None, None
            return pool_id, pool_addr, token0, token1, reserve0, reserve1, blocknr
        except ProtocolError:
            pass



class Runner:
    log = getLogger(__name__)

    def __init__(self, args: Args):
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()
        self.pools_cache = dict()  # addr->db_id
        self.tokens_cache = dict()  # addr->db_id
        self.latest_blocknr = 0

    @property
    def w3(self):
        try:
            return self.__w3
        except AttributeError:
            self.__w3 = Web3Connector.get_connection(self.args.web3_rpc_url)
        return self.__w3

    def preload_existing_from_db(self):
        with self.db as curs:
            for id, addr in curs.execute("SELECT id, address FROM tokens").get_all():
                self.tokens_cache[addr] = id
            self.log.info("%u tokens preloaded from db", len(self.tokens_cache))
            for id, addr in curs.execute("SELECT id, address FROM pools").get_all():
                self.pools_cache[addr] = id
            self.log.info("%u pools preloaded from db", len(self.pools_cache))

    def __call__(self):
        with self.db as curs:
            exchange_id = curs.add_exchange(self.args.router_address, self.args.exchange_name, ignore_duplicates=True)
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
                            yield factory_addr, i, self.args.reserves
                    for res in executor.map(do_work, sequence(), chunksize=100):
                        if progress():
                            self.db.commit()
                        if not res:
                            # the call failed
                            continue
                        pool_id, pool_addr, token0, token1, reserve0, reserve1, blocknr = res
                        pid = self.pools_cache.get(pool_addr)
                        if pid is None:
                            if token0 == token1:
                                self.log.warning("pool %s appears to be circular on token %s: skipped", pool_addr,
                                                 token0)
                                continue
                            tid0 = self.tokens_cache.get(token0)
                            if tid0 is None:
                                tid0 = self.tokens_cache[token0] = curs.add_token(token0, ignore_duplicates=True)
                            tid1 = self.tokens_cache.get(token1)
                            if tid1 is None:
                                tid1 = self.tokens_cache[token1] = curs.add_token(token1, ignore_duplicates=True)
                            pid = curs.add_swap(address=pool_addr
                                                , exchange_id=exchange_id
                                                , token0_id=tid0
                                                , token1_id=tid1
                                                , ignore_duplicates=True)
                            self.pools_cache[pool_addr] = pid
                        if reserve0 and reserve1 and blocknr:
                            curs.add_pool_reserve(pid, reserve0, reserve1)
                            if blocknr > self.latest_blocknr:
                                self.latest_blocknr = blocknr

            curs.reserves_block_number = self.latest_blocknr


def main():
    basicConfig(level="INFO")
    args = Args.from_cmdline(__doc__)
    runner = Runner(args)
    runner.preload_existing_from_db()
    runner()


if __name__ == '__main__':
    main()