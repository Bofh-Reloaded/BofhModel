from os.path import join, isdir, isfile

import networkx as nx
import sqlite3

STATUS_DB = "status.db"
SWAPS_DB = "prediction_swaps.db"


class IdealPool:
    """Represents an ideal pool. It has a swap() function which hopefully mimics what would happen in a real AMM LP"""

    DEFAULT_SWAP_FEE_PERCENT = 0.3
    __slots__ = ("token0", "token1", "reserve0", "reserve1", "swapFeePct","address")

    def __init__(self, token0: int, token1: int, reserve0: int, reserve1: int, address: str, swapFeePct=DEFAULT_SWAP_FEE_PERCENT, **discard_kwargs):
        assert isinstance(token0, int)
        assert isinstance(token1, int)
        assert isinstance(reserve0, int)
        assert isinstance(reserve1, int)
        assert isinstance(address, str)
        self.token0 = token0
        self.token1 = token1
        self.reserve0 = reserve0
        self.reserve1 = reserve1   
        self.swapFeePct = swapFeePct
        self.address = address
        
    def flip(self) : 
        return self.__class__(self.token1, self.token0, self.reserve1, self.reserve0, self.address)
        

    def swap(self, requestedToken, requestedAmountOut, update_reserves=False) -> int:
        """Attempts to replicate AMM behavior.
           Call using the requested OUT token (the one which you want to receive from the swap), and its desired amount.
           The call returns the prospected amount of token IN which has to be deposited in order to perform the swap.
           The update_reserves parameter controls whether the reserves of the swap are actually updated or not.

           All balances are expressed in Wei. DON'T USE FLOAT."""
        assert requestedToken in (self.token0, self.token1)
        assert isinstance(requestedAmountOut, int)
        if requestedToken == self.token0:
            tokenOutReserveBefore = self.reserve0
            tokenInReserveBefore = self.reserve1
        else:
            tokenOutReserveBefore = self.reserve1
            tokenInReserveBefore = self.reserve0

        assert requestedAmountOut <= tokenOutReserveBefore
        tokenOutReserveMidpoint = tokenOutReserveBefore - (requestedAmountOut // 2)
        tokenOutAppliedPrice = (tokenInReserveBefore / tokenOutReserveMidpoint) * (100.0 + self.swapFeePct) / 100.0
        tokenInNecessaryAmount = int(tokenOutAppliedPrice * requestedAmountOut)
        if update_reserves:
            tokenOutReserveAfter = tokenOutReserveBefore - requestedAmountOut
            if requestedToken == self.token0:
                self.reserve0 = tokenOutReserveAfter
                self.reserve1 = tokenInReserveBefore + tokenInNecessaryAmount
            else:
                self.reserve1 = tokenOutReserveAfter
                self.reserve0 = tokenInReserveBefore + tokenInNecessaryAmount
        return tokenInNecessaryAmount

class Cached:
    status_db_fpath=None

def load_graph_from_db_directory(dp_dump_directory=None):
    status_db = Cached.status_db_fpath
    if not status_db:
        while not dp_dump_directory or not isdir(dp_dump_directory) or not isfile(join(dp_dump_directory, STATUS_DB)):
            dp_dump_directory = input("Enter DB directory (expected files: status.db and prediction_swaps.db) > ")

        # 1. open the thing, list all tokens and all swaps
        status_db = join(dp_dump_directory, STATUS_DB)
        Cached.status_db_fpath = status_db
    conn = sqlite3.connect(status_db)
    curs = conn.cursor()
    G = nx.MultiDiGraph()

    print("Loading tokens and swaps from", status_db, "...")
    curs.execute("SELECT id, address FROM tokens")
    while True:
        rec = curs.fetchone()
        if not rec: break
        G.add_node(rec[0], address=rec[1])

    if False:
        # OCCOSE??
        threshold = 2
        f = f"token0_id IN (SELECT token0_id FROM pools GROUP BY token0_id HAVING COUNT(token1_id) > {threshold})"
        curs.execute(f"SELECT id, token0_id, token1_id, address FROM pools WHERE {f}")
    else:
        curs.execute(f"SELECT id, token0_id, token1_id, address FROM pools")
    pools = dict()
    while True:
        rec = curs.fetchone()
        if not rec: break
        pools[rec[0]] = dict(token0=rec[1], token1=rec[2], address=rec[3])

    print(f"pools {len(pools)}")

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
            pool.update(reserve0=int(rec[1]), reserve1=int(rec[2]))

    edge_ctr = 0
    for id, pool in pools.items():
        token0 = pool["token0"]
        token1 = pool["token1"]
        if "reserve0" not in pool:
            # Do not bless the arches with a pool object. Reserves db is not available
            pool = None
            G.add_edge(token0, token1, pool=pool)
            G.add_edge(token1, token0, pool=pool)
        else:
            pool = IdealPool(**pool)
            G.add_edge(token0, token1, pool=pool)
            G.add_edge(token1, token0, pool=pool.flip())
        edge_ctr += 2
    print("numero di edges caricati da db:", edge_ctr)

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
        yield dict(tokenIn=rec[0], tokenOut=rec[1], balanceIn=int(rec[2]), balanceOut=int(rec[3]))

def get_start_node_id(dp_dump_directory=None):
    status_db = Cached.status_db_fpath
    if not status_db:
        while not dp_dump_directory or not isdir(dp_dump_directory) or not isfile(join(dp_dump_directory, STATUS_DB)):
            dp_dump_directory = input("Enter DB directory (expected files: status.db and prediction_swaps.db) > ")

        # 1. open the thing, list all tokens and all swaps
        status_db = join(dp_dump_directory, STATUS_DB)
        Cached.status_db_fpath = status_db
    conn = sqlite3.connect(status_db)
    curs = conn.cursor()
    curs.execute(f"select id from tokens where address in (select value from status_meta where key = 'start_token_address')")
    res = None
    for i in curs.fetchone():
        res = i
    conn.close()
    if not isinstance(res, int):
        raise RuntimeError("start_token_address not saved in db")
    return res

def get_stable_nodes_id(dp_dump_directory=None):
    status_db = Cached.status_db_fpath
    if not status_db:
        while not dp_dump_directory or not isdir(dp_dump_directory) or not isfile(join(dp_dump_directory, STATUS_DB)):
            dp_dump_directory = input("Enter DB directory (expected files: status.db and prediction_swaps.db) > ")

        # 1. open the thing, list all tokens and all swaps
        status_db = join(dp_dump_directory, STATUS_DB)
        Cached.status_db_fpath = status_db
    conn = sqlite3.connect(status_db)
    curs = conn.cursor()
    curs.execute(f"select id from tokens where is_stabletoken")
    res = []
    while True:
        rec = curs.fetchone()
        if not rec: break
        res.append(rec[0])
    conn.close()
    if not res:
        raise RuntimeError("stable_tokens not saved in db")
    return res


if __name__ == '__main__':
    load_graph_from_db_directory(".")
    for i in load_predicted_swap_events("."): print(i)
