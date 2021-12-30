from asyncio import get_event_loop
from time import sleep

from jsonrpc_websocket import Server

from bofh.utils.web3 import Web3Connector, Web3PoolExecutor, JSONRPCConnector, method_id

__doc__="""Start model runner.

Usage: bofh.model.runner1 [options]

Options:
  -h  --help
  -d, --dsn=<connection_str>    DB dsn connection string [default: sqlite3://status.db]
  -c, --connection_url=<url>    Web3 RPC connection URL [default: %s]
  -n <n>                        number of pools to query before exit (benchmark mode)
  -j <n>                        number of RPC data ingest workers, default one per hardware thread. Only used during initialization phase
  -v, --verbose                 debug output
  --chunk_size=<n>              preloaded work chunk size per each worker [default: 100]
  --pred_polling_interval=<n>   Web3 prediction polling internal in millisecs [default: 1000]
""" % Web3Connector.DEFAULT_URI_WSRPC

from dataclasses import dataclass
from logging import getLogger, basicConfig

from bofh.model.database import ModelDB
from bofh_model_ext import TheGraph


PREDICTION_LOG_TOPIC0 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"  # Keccak256("Swap(address,uint256,uint256,uint256,uint256,address)")


@dataclass
class Args:
    status_db_dsn: str = None
    verbose: bool = False
    pools_limit: int = 0
    web3_rpc_url: str = None
    max_workers: int = 0
    chunk_size: int = 0
    pred_polling_interval: int = 0

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
            , pred_polling_interval=int(cls.default(args["--pred_polling_interval"], 1000))
        )


def getReserves(pool_address):
    """Invoke local execution of PoolContract.getReserves() on the EVM for the specified pool.
       Returns a tuple of (pool_address, reserve0, reserve1).

       This function is meant to be executed across an IPC multiprocess turk for massive parallelism.

       It reuses its web3 connection and assets to improve batch performance.

       It also avoids usage of the web3 framework which has shown flaky performances in the past. It does
       the dirty handling inline, and calls a remote RPC at the lowest possible level."""
    try:
        exe = getReserves.exe
        ioloop = getReserves.ioloop
        mid = getReserves.mid
    except AttributeError:
        exe = getReserves.exe = JSONRPCConnector.get_connection()
        ioloop = getReserves.ioloop = get_event_loop()
        mid = getReserves.mid = method_id("getReserves()")
    fut = exe.eth_call({"to": pool_address, "data": mid}, "latest")
    res = ioloop.run_until_complete(fut)
    # at this point "res" should be a long 0xhhhhh... byte hexstring.
    # it should be composed of 3 32-bytes big-endian values. In sequence:
    # - reserve0
    # - reserve1
    # - blockTimestampLast (mod 2**32) of the last block during which an interaction occured for the pair.
    try:
        if not res or not res.startswith("0x") or not len(res) != 66:
            raise ValueError
        ofs = 2
        reserve0 = int(res[ofs:ofs + 64], 16)
        ofs += 64
        reserve1 = int(res[ofs:ofs + 64], 16)
        ofs += 64
        blockTimestampLast = int(res[ofs:ofs + 64], 16)
        return (pool_address
                , reserve0
                , reserve1
                , blockTimestampLast
                )
    except:
        print("invalid response (expected 96-byte hexstring):", res)
        return pool_address, None, None


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
        self.skip = 0
        self.tot = 0
        self.ioloop = get_event_loop()
        # self.polling_started = Event()

    @property
    def pools_ctr(self):
        return len(self.pools_map)

    def preload_exchanges(self):
        self.log.info("preloading exchanges...")
        with self.db as curs:
            for id, *args in curs.list_exchanges():
                addr = self.graph.add_exchange(*args)
                assert addr is not None
                self.exchanges_map[id] = addr

    def preload_tokens(self):
        self.log.info("preloading tokens...")
        with self.db as curs:
            for id, *args, is_stabletoken in curs.list_tokens():
                addr = self.graph.add_token(*args, bool(is_stabletoken))
                if addr is None:
                    raise RuntimeError("integrity error: token address is already not of a token: id=%r, %r" % (id, args))
                self.tokens_map[id] = addr

    def preload_pools(self):
        self.log.info("preloading pools...")
        with self.db as curs:
            for id, address, exchange_id, token0_id, token1_id in curs.list_pools():
                addr = self.graph.add_swap_pair(address, self.tokens_map[token0_id], self.tokens_map[token1_id])
                self.tot += 1
                if addr is None:
                    self.skip += 1
                    self.log.warning("integrity error: token address is already not of a pool: id=%r, %r -- skip %r over %r", id, address, self.skip, self.tot)
                else:
                    self.pools_map[id] = addr
                if self.args.pools_limit and self.pools_ctr >= self.args.pools_limit:
                    self.log.info("stopping after loading %r pools, as per effect of -n cli parameter", self.pools_ctr)
                    break

    def pools_iterator(self):
        for pool in self.pools_map.values():
            yield str(pool.address)

    def preload_balances(self):
        self.log.info("fetching balances via Web3...")
        with Web3PoolExecutor(connection_uri=self.args.web3_rpc_url, max_workers=self.args.max_workers) as executor:
            self.log.info("fetching balances via Web3:"
                     "\n\t- %r pool getReserve requests"
                     "\n\t- on Web3 servant at %s"
                     "\n\t- using %d workers"
                     "\n\t- each with a %d preload queue"
                      , self.pools_ctr
                      , self.args.web3_rpc_url
                      , self.args.max_workers
                      , self.args.chunk_size
                      )
            for pool_addr, reserve0, reserve1, blockTimestampLast in executor.map(getReserves, self.pools_iterator(), chunksize=self.args.chunk_size):
                pair = self.graph.lookup_swap_pair(pool_addr)
                if not pair:
                    raise IndexError("unknown pool: %s" % pool_addr)
                # reset pool reserves
                pair.reserve0, pair.reserve1 = reserve0, reserve1

            executor.shutdown(wait=True)

    async def prediction_polling_task(self):
        # await self.polling_started.wait()
        server = Server(self.args.web3_rpc_url)
        self.latestBlockNumber = 0
        try:
            await server.ws_connect()
            while True:  # self.polling_started.is_set():
                result = await server.eth_consPredictLogs(0, 0, PREDICTION_LOG_TOPIC0)
                if result and result.get("logs"):
                    blockNumber = result["blockNumber"]
                    if blockNumber > self.latestBlockNumber:
                        self.latestBlockNumber = blockNumber
                        self.log.info("block %r, found %r log predictions" % (self.latestBlockNumber, len(result["logs"])))
                        for log in result["logs"]:
                            self.log.info("log %r@tx %s data: %s", int(log["logIndex"], 16), log["tx"], log["data"], )
                            tx = await server.eth_getTransactionByHash(log["tx"])
                            if tx:
                                pool_addr = tx["to"]
                                pool = self.graph.lookup_swap_pair(pool_addr)
                                if pool:
                                    print("known pool", pool_addr)
                sleep(self.args.pred_polling_interval * 0.001)
        except:
            self.log.exception("Error in prediction polling thread")
        finally:
            await server.close()

    def poll_prediction(self):
        self.ioloop.run_until_complete(self.prediction_polling_task())

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
    runner.preload_balances()
    runner.poll_prediction()


if __name__ == '__main__':
    main()