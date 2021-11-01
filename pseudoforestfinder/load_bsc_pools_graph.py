from os.path import dirname, realpath, join

dir_path = dirname(dirname(realpath(__file__)))
bsc_pools_dat = join(dir_path, "test", "bsc_pools.data.gz")

import networkx as nx
import json
import gzip

def load_graph_from_json_coso(filepath=bsc_pools_dat):
    # 1. open the thing, list all tokens and all swaps
    with gzip.open(filepath) as fd:
        data = json.load(fd)

    known_tokens = dict()  # address -> int(id)
    known_pairs = dict()  # address -> (token_id0, token_id1)
    for k, v in data.items():
        for blah, exchange in v.items():
            for pool in exchange["pools"]:
                token0 = pool["token0"]
                token1 = pool["token1"]
                swap_addr = pool["address"]
                for t in token0, token1:
                    if t not in known_tokens:
                        known_tokens[t] = len(known_tokens)+1
                assert swap_addr not in known_pairs
                known_pairs[swap_addr] = (known_tokens[token0], known_tokens[token1])
    G = nx.MultiDiGraph()
    G.add_nodes_from(known_tokens.values())
    for k, v in known_pairs.items():
        G.add_edge(*v)
    return G


if __name__ == '__main__':
    load_graph_from_json_coso()
