"""Import BSC pools from CTPGO pools.json datafile.

Usage: bofh.model.import_ctpgo_pools [options] <exchange_name> <ctpgo_pools_json_file>

Options:
  -h  --help
  -d, --dsn=<connection_str>    DB dsn connection string [default: sqlite3://status.db]
  -v, --verbose                 debug output
  --skip_duplicates             skip token and swap duplicates
"""
from logging import basicConfig

from docopt import docopt

from bofh.model.database import ModelDB, StatusScopedCursor
import json


def import_pools_and_tokens_from_json_coso(exchange_name, filepath, db: ModelDB, ignore_duplicates=False):
    opener = open
    if filepath.endswith(".gz"):
        import gzip
        opener = gzip.open
    # 1. open the thing, list all tokens and all swaps
    with opener(filepath) as fd:
        data = json.load(fd)
    known_tokens = dict()  # address -> int(id)
    with db as curs:
        exchange_id = curs.add_exchange(exchange_name, ignore_duplicates=True)
        for pool in data:
            token0 = pool["Token0"]
            token1 = pool["Token1"]
            token0 = token0.lower()
            token1 = token1.lower()
            if token0 > token1:
                token0, token1 = token1, token0
            token0 = known_tokens.get(token0, token0)
            token1 = known_tokens.get(token1, token1)
            for tok in token0, token1:
                if not isinstance(tok, int):
                    i = curs.add_token(tok, ignore_duplicates=True)
                    assert isinstance(i, int)
                    known_tokens[tok] = i
            if not isinstance(token0, int): token0 = known_tokens[token0]
            if not isinstance(token1, int): token1 = known_tokens[token1]
            assert isinstance(token0, int)
            assert isinstance(token1, int)
            swap_addr = pool["Address"]
            swap_addr = swap_addr.lower()
            curs.add_swap(address=swap_addr
                          , exchange_id=exchange_id
                          , token0_id=token0
                          , token1_id=token1
                          , ignore_duplicates=ignore_duplicates)

def main():
    arguments = docopt(__doc__)
    basicConfig(level=arguments["--verbose"] and "DEBUG" or "INFO")
    db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=arguments["--dsn"])
    db.open_and_priming()
    import_pools_and_tokens_from_json_coso(arguments["<exchange_name>"]
                                           , arguments["<ctpgo_pools_json_file>"]
                                           , db
                                           , ignore_duplicates=arguments["--skip_duplicates"])


if __name__ == '__main__':
    main()
