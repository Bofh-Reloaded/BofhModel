__doc__="""Manage stabletokens.

Usage: bofh.model.manage_stabletokens [options]

Options:
  -h  --help
  -d, --dsn=<connection_str>            DB dsn connection string [default: sqlite3://status.db]
  -l, --list                            list current stabletoken set
  -q, --statistic                       list most occurring coins according to pools population
  -a, --add                             add stabletokens from stdin (by id or address)
  -r, --remove                          remove stabletokens from stdin (by id or address)
  --id                                  print ids only
  --address                             print address only
  --symbol                              print symbol
  --limit=<n>                           limit list output [default: 10]
"""

from dataclasses import dataclass
from logging import getLogger, basicConfig
from tabulate import tabulate

from bofh.model.database import ModelDB, StatusScopedCursor


@dataclass
class Args:
    status_db_dsn: str = None
    list: bool = False
    statistic: bool = False
    add: bool = False
    remove: bool = False
    id: bool = False
    address: bool = False
    symbol: bool = False
    limit: int = 0

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
            , list=args["--list"]
            , statistic=args["--statistic"]
            , add=args["--add"]
            , remove=args["--remove"]
            , id=args["--id"]
            , address=args["--address"]
            , symbol=args["--symbol"]
            , limit=int(args["--limit"])
        )


class Runner:
    log = getLogger(__name__)

    def __init__(self, args: Args):
        self.args = args
        self.db = ModelDB(schema_name="status", cursor_factory=StatusScopedCursor, db_dsn=self.args.status_db_dsn)
        self.db.open_and_priming()

    def get_tokens_stat(self):
        with self.db as curs:
            limit = self.args.limit and ("LIMIT %u" % self.args.limit) or ""
            return curs.execute(f"""
                SELECT t.id, (q0.ctr+q1.ctr) AS occurrence, t.address, t.symbol, t.name, t.is_stabletoken FROM tokens AS t
                JOIN
                    (SELECT token0_id AS tid, COUNT(1) AS ctr FROM pools GROUP BY token0_id ORDER BY ctr DESC) AS q0 ON t.id=q0.tid
                JOIN
                    (SELECT token1_id AS tid, COUNT(1) AS ctr FROM pools GROUP BY token1_id ORDER BY ctr DESC) AS q1 ON t.id=q1.tid
                WHERE NOT t.disabled
                ORDER BY (q0.ctr+q1.ctr) DESC {limit};
                """).get_all()

    def lookup_token(self, key):
        try:
            key = int(key)
        except ValueError:
            # key is not an int
            try:
                int(key, 16)
            except:
                # not an address either
                raise ValueError(f"not an integer or an address: {key}")
        try:
            with self.db as curs:
                if isinstance(key, int):
                    return curs.execute("SELECT id, address, symbol, name FROM tokens WHERE id = ? AND NOT disabled", (key,)).get()
                if isinstance(key, str):
                    return curs.execute("SELECT id, address, symbol, name FROM tokens WHERE address = ? AND NOT disabled", (key,)).get()
        except:
            pass

    def __call__(self, *args, **kwargs):
        if self.args.add:
            self.add()
        elif self.args.remove:
            self.remove()
        elif self.args.statistic:
            self.statistic()
        else:
            self.list()

    def statistic(self):
        short = []
        table = []
        for id, occur, addr, symbol, name, ist in self.get_tokens_stat():
            k = []
            if self.args.id:
                k.append(id)
            if self.args.address:
                k.append(addr)
            if self.args.symbol:
                k.append(symbol)
            if k:
                short.append(k)
            table.append([id, occur, addr, symbol, name, ist and "yes" or "no"])
        if short:
            for k in short:
                print(*k)
        else:
            print(tabulate(table, headers=["id", "occurr", "address", "symbol", "name", "stable"], tablefmt="orgtbl"))

    def list(self):
        short = []
        table = []
        for id, addr, symbol, name in self.db.cursor().execute(f"SELECT id, address, symbol, name FROM tokens WHERE is_stabletoken ORDER BY id").get_all():
            k = []
            if self.args.id:
                k.append(id)
            if self.args.address:
                k.append(addr)
            if self.args.symbol:
                k.append(symbol)
            if k:
                short.append(k)
            table.append([id, addr, symbol, name])
        if short:
            for k in short:
                print(*k)
        else:
            print(tabulate(table, headers=["id", "address", "symbol", "name"], tablefmt="orgtbl"))

    def read_ids_from_stdin(self):
        try:
            while True:
                for s in input().split():
                    try:
                        yield int(s)
                        continue
                    except ValueError:
                        pass
                    try:
                        int(s, 16)
                        yield s
                        continue
                    except ValueError:
                        pass
                    continue
        except EOFError:
            pass

    def add(self):
        all = []
        for key in self.read_ids_from_stdin():
            res = self.lookup_token(key)
            if res:
                all.append(res)
        with self.db as curs:
            for id, address, symbol, name in all:
                self.log.info(f"set token {name} ({symbol}), address {address} as stabletoken")
                curs.execute("UPDATE tokens SET is_stabletoken = 1 WHERE id = ?", (id, ))

    def remove(self):
        all = []
        for key in self.read_ids_from_stdin():
            res = self.lookup_token(key)
            if res:
                all.append(res)
        with self.db as curs:
            for id, address, symbol, name in all:
                self.log.info(f"removing token {name} ({symbol}), address {address} from stabletokens")
                curs.execute("UPDATE tokens SET is_stabletoken = 0 WHERE id = ?", (id, ))


def main():
    basicConfig(level="INFO")
    args = Args.from_cmdline(__doc__)
    bofh = Runner(args)
    bofh()


if __name__ == '__main__':
    main()