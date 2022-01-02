from os.path import dirname, realpath, join, isdir, isfile

dir_path = dirname(dirname(realpath(__file__)))
bsc_pools_dat = join(dir_path, "test", "bsc_pools.data.gz")

import networkx as nx
import sqlite3

STATUS_DB = "status.db"
SWAPS_DB = "prediction_swaps.db"


def load_graph_from_db_directory(dp_dump_directory=None):
    while not dp_dump_directory or not isdir(dp_dump_directory) or not isfile(join(dp_dump_directory, STATUS_DB)):
        dp_dump_directory = input("Enter DB directory (expected files: status.db and prediction_swaps.db) > ")

    # 1. open the thing, list all tokens and all swaps
    status_db = join(dp_dump_directory, STATUS_DB)
    conn = sqlite3.connect(status_db)
    curs = conn.cursor()
    G = nx.MultiDiGraph()

    print("Loading tokens and swaps from", status_db, "...")
    curs.execute("SELECT id, address FROM tokens")
    while True:
        rec = curs.fetchone()
        if not rec: break
        G.add_node(rec[0], address=rec[1])

    curs.execute("SELECT id, token0_id, token1_id, address FROM pools")
    pools = dict()
    while True:
        rec = curs.fetchone()
        if not rec: break
        pools[rec[0]] = dict(token0=rec[1], token1=rec[2], address=rec[3])

    # 2. open the prediction_swaps db, if available. load balances from there
    conn.close()

    pred_db = join(dp_dump_directory, SWAPS_DB)
    if isfile(pred_db):
        print(pred_db, "Database found! Loading pool reserves from it ...")
        print("NOTE: thanks to this, each networkx graph edge will have a valid couple of reserve0, reserve1 attribute")
        conn = sqlite3.connect(pred_db)
        curs = conn.cursor()
        curs.execute("SELECT pool, reserve0, reserve1 FROM pool_reserves")
        while True:
            rec = curs.fetchone()
            if not rec: break
            pool = pools.get(rec[0])
            if not pool: continue
            pool.update(reserve0=int(rec[1]), reserve1=(rec[2]))

    for id, pool in pools.items():
        token0 = pool.pop("token0")
        token1 = pool.pop("token1")
        G.add_edge(token0, token1, **pool)

    return G


def load_predicted_swap_events(dp_dump_directory=None, start_from_blocknr=0):
    while not dp_dump_directory or not isdir(dp_dump_directory) or not isfile(join(dp_dump_directory, SWAPS_DB)):
        dp_dump_directory = input("Enter DB directory (expected file: prediction_swaps.db) > ")
    pred_db = join(dp_dump_directory, SWAPS_DB)
    print("Loading swap events from ", pred_db)
    conn = sqlite3.connect(pred_db)
    curs = conn.cursor()
    curs.execute("SELECT tokenIn, tokenOut, balanceIn, balanceOut FROM swap_logs WHERE block_nr >= ? ORDER BY id"
                 , (start_from_blocknr, ))
    while True:
        rec = curs.fetchone()
        if not rec: break
        yield dict(tokenIn=rec[0], tokenOut=rec[1], balanceIn=rec[2], balanceOut=rec[3])


if __name__ == '__main__':
    load_graph_from_db_directory(".")
    for i in load_predicted_swap_events("."): print(i)
