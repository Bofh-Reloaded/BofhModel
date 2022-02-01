from asyncio import get_event_loop

from jsonrpc_base import ProtocolError

from bofh.utils.misc import progress_printer, optimal_cpu_threads
from bofh.utils.solidity import get_abi
from bofh.utils.web3 import Web3Connector, JSONRPCConnector, method_id, encode_uint, Web3PoolExecutor, \
    parse_data_address

__doc__="""Start model runner.

Usage: bofh.model.download_uniswap_exchange [options] <exchange_name> <router_address>

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



@dataclass
class Args:
    status_db_dsn: str = None
    verbose: bool = False
    web3_rpc_url: str = None
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
            , max_workers=int(cls.default(args["-j"], 0))
            , exchange_name=args["<exchange_name>"]
            , router_address=args["<router_address>"]
        )


def getPair(args):
    factory_address, pair_idx = args
    try:
        exe = getPair.exe
        ioloop = getPair.ioloop
        mid = getPair.mid
    except AttributeError:
        exe = getPair.exe = JSONRPCConnector.get_connection()
        ioloop = getPair.ioloop = get_event_loop()
        mid = getPair.mid = method_id("allPairs(uint256)")
    for i in range(4):  # make two attempts
        data = mid+encode_uint(pair_idx)
        fut = exe.eth_call({"to": factory_address, "data": data}, "latest")
        res = ioloop.run_until_complete(fut)
        return pair_idx, parse_data_address(res)


def getTokens(pool_id, pool_addr):
    try:
        exe = getPair.exe
        ioloop = getPair.ioloop
        t0 = getPair.t0
        t1 = getPair.t1
    except AttributeError:
        exe = getPair.exe = JSONRPCConnector.get_connection()
        ioloop = getPair.ioloop = get_event_loop()
        t0 = getPair.t0 = method_id("token0()")
        t1 = getPair.t1 = method_id("token0()")
    for i in range(4):  # make two attempts
        try:
            fut = exe.eth_call({"to": pool_addr, "data": t0}, "latest")
            res0 = ioloop.run_until_complete(fut)
            fut = exe.eth_call({"to": pool_addr, "data": t1}, "latest")
            res1 = ioloop.run_until_complete(fut)
            return pool_id, pool_addr, parse_data_address(res0), parse_data_address(res1)
        except ProtocolError:
            return None



class Runner:
    log = getLogger(__name__)

    def __init__(self, args: Args):
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()

    @property
    def w3(self):
        try:
            return self.__w3
        except AttributeError:
            self.__w3 = Web3Connector.get_connection(self.args.web3_rpc_url)
        return self.__w3

    def __call__(self):
        with self.db as curs:
            tokens_addr_to_id = dict()
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
                with Web3PoolExecutor(connection_uri=self.args.web3_rpc_url, max_workers=self.args.max_workers) as executor1, \
                        Web3PoolExecutor(connection_uri=self.args.web3_rpc_url, max_workers=self.args.max_workers) as executor2 \
                        :
                    def args():
                        for i in range(pairs_nr):
                            yield factory_addr, i
                    for pair_idx, pair_address in executor1.map(getPair, args(), chunksize=executor1.max_workers*100):
                        res = executor2.submit(getTokens, pair_idx, pair_address).result()
                        if not res:
                            continue
                        pool_id, pool_addr, token0, token1 = res
                        tid0 = tokens_addr_to_id.get(token0)
                        if tid0 is None:
                            tid0 = tokens_addr_to_id[token0] = curs.add_token(token0, ignore_duplicates=True)
                        tid1 = tokens_addr_to_id.get(token1)
                        if tid1 is None:
                            tid1 = tokens_addr_to_id[token1] = curs.add_token(token1, ignore_duplicates=True)
                        curs.add_swap(address=pool_addr
                                      , exchange_id=exchange_id
                                      , token0_id=tid0
                                      , token1_id=tid1
                                      , ignore_duplicates=True)
                        if progress():
                            self.db.commit()
                    executor1.shutdown()
                    executor2.shutdown()




def main():
    basicConfig(level="INFO")
    args = Args.from_cmdline(__doc__)
    runner = Runner(args)
    runner()


if __name__ == '__main__':
    main()