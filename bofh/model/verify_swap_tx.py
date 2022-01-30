from asyncio import get_event_loop
from random import choice

from hexbytes import HexBytes

from bofh.model.runner1 import PREDICTION_LOG_TOPIC0_SWAP, PREDICTION_LOG_TOPIC0_SYNC
from bofh.utils.misc import LogAdapter
from bofh.utils.web3 import Web3Connector, log_topic_id, parse_data_parameters


__doc__="""Observes an Uniswap-AMM swap transaction and crunch some numbers.

Usage: bofh.model.verify_swap_tx [options] <txhash>

Options:
  -h  --help
  -c, --connection_url=<url>            Web3 RPC connection URL [default: %s]
  -v, --verbose                         debug output
""" % (Web3Connector.DEFAULT_URI_WSRPC, )

from dataclasses import dataclass
from logging import getLogger, basicConfig

from bofh_model_ext import TheGraph, log_level, log_register_sink, log_set_level




@dataclass
class Args:
    verbose: bool = False
    web3_rpc_url: str = None
    txhash: str = None

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
            txhash = args["<txhash>"]
            , verbose=bool(cls.default(args["--verbose"], 0))
            , web3_rpc_url=cls.default(args["--connection_url"], 0)
        )


class Runner:

    def __init__(self, args: Args):
        self.log = getLogger("verify_swap_tx")
        self.log.setLevel(args.verbose and "DEBUG" or "INFO")
        self.graph = TheGraph()
        self.args = args
        self.ioloop = get_event_loop()
        self.pool = self.setup_pool()

    def setup_pool(self):
        exchange = self.graph.add_exchange(1, self.random_address(), "MockExchange")
        t0 = self.graph.add_token(2, self.random_address(), "TOK0", "TOK0", 18, 0)
        t1 = self.graph.add_token(3, self.random_address(), "TOK1", "TOK1", 18, 0)
        return self.graph.add_lp(4, self.random_address(), exchange, t0, t1)

    @staticmethod
    def random_address():
        res = "0x"
        hex = "0123456789abcdef"
        for i in range(40):
            res += choice(hex)
        return res

    def __call__(self):
        w3 = Web3Connector.get_connection(self.args.web3_rpc_url)
        tx = w3.eth.get_transaction(self.args.txhash)
        logs = w3.eth.get_transaction_receipt(self.args.txhash)
        for l in logs["logs"]:
            topics = l.get("topics")
            topic_swap = HexBytes(PREDICTION_LOG_TOPIC0_SWAP)
            topic_sync = HexBytes(PREDICTION_LOG_TOPIC0_SYNC)
            if not topics:
                self.log.error("no logs in transaction")
                return 1
            if topics[0] == topic_sync:
                data = l["data"]
                reserves = parse_data_parameters(data)
                self.log.debug("reserves updated via Sync event: reserve0 = %r, reserve1 = %r", *reserves)
                self.pool.setReserves(*reserves)
            if topics[0] == topic_swap:
                data = l["data"]
                amount0In, amount1In, amount0Out, amount1Out = parse_data_parameters(data)
                if amount0In and amount1In:
                    self.log.error("this is a two-way swap: amount0In=%r and amount1In=%r [UNIMPLEMENTED!]"
                                   , amount0In, amount1In)
                    return 1
                if not amount0In and not amount1In:
                    self.log.error("swap log with zero balance (no exchange of token amount)")
                    return 1
                if amount0In:
                    if amount1Out == 0:
                        self.log.warning("amount0In > 0 (%r): expected amount1Out > 0 but isn't"
                                         , amount0In)
                        return 1
                    self.log.info("amount0In=%r, amount1Out=%r (this is a token0->token1 swap)", amount0In, amount1Out)
                    balanceA = self.pool.SwapExactTokensForTokens(self.pool.token0, amount0In)
                    self.log.info("amount1Out computed internally via SwapExactTokensForTokens: %r", balanceA)
                    gap = abs(int(str(balanceA))-amount1Out)
                    self.log.info("result error is %r (%0.05f%%)", gap, 100*(gap/amount1Out))

                    balanceB = self.pool.SwapTokensForExactTokens(self.pool.token1, amount1Out)
                    self.log.info("amount0In computed internally via SwapTokensForExactTokens: %r", balanceB)
                    gap = abs(int(str(balanceB))-amount0In)
                    self.log.info("result error is %r (%0.05f%%)", gap, 100*(gap/amount0In))
                if amount1In:
                    if amount0Out == 0:
                        self.log.warning("amount1In > 0 (%r): expected amount0Out > 0 but isn't"
                                         , amount1In)
                        return 1
                    self.log.info("amount1In=%r, amount0Out=%r (this is a token1->token0 swap)", amount1In, amount0Out)
                    balanceA = self.pool.SwapExactTokensForTokens(self.pool.token1, amount1In)
                    self.log.info("amount0Out computed internally via SwapExactTokensForTokens: %r", balanceA)
                    gap = abs(int(str(balanceA))-amount0Out)
                    self.log.info("result error is %r (%0.05f%%)", gap, 100*(gap/amount0Out))

                    balanceB = self.pool.SwapTokensForExactTokens(self.pool.token0, amount0Out)
                    self.log.info("amount1In computed internally via SwapTokensForExactTokens: %r", balanceB)
                    gap = abs(int(str(balanceB))-amount1In)
                    self.log.info("result error is %r (%0.05f%%)", gap, 100*(gap/amount1In))




def main():
    args = Args.from_cmdline(__doc__)
    basicConfig(level="INFO")
    log_set_level(log_level.debug)
    log_register_sink(LogAdapter(level=args.verbose and "DEBUG" or "INFO"))
    runner = Runner(args)
    runner()


if __name__ == '__main__':
    main()