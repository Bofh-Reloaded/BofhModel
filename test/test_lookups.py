from bofh_model_ext import *

def test_lookups():
    graph = TheGraph()
    graph.add_exchange(1, "0x493631F57d1FD97FBA82E9613E832914c0144622", "TestExchange", 2500)
    graph.add_token(1, "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82", "PancakeSwap Token", "Cake", 18, True)
    graph.add_token(2, "0xe9e7cea3dedca5984780bafc599bd69add087d56", "BUSD Token", "BUSD", 18, True)
    graph.add_token(3, "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd", "Wrapped-BNB", "WBNB", 18, True)
    p0 = graph.add_lp(1, "0xb51e4d3F60c8453AdCa52797F9FA1481A6E13A7A", 1, 3, 2)
    p1 = graph.add_lp(2, "0x54a2028b7A59C6e8e62852CAE8D38f7958851F7c", 1, 2, 1)
    p2 = graph.add_lp(3, "0xDD4bDb1e31c6A5Edb0E96E61A05E2664bCDe578A", 1, 3, 1)
    path = graph.add_path(p0, p1, p2)
    print(path, path.id())

if __name__ == '__main__':
    test_lookups()