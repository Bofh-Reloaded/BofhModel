"""Usage: load_pools_json.py [options] [<input_file>]

Options:
  -h --help
  -o, --output file SQLite database file (create if not existing)

"""

from os.path import join
from docopt import docopt


class StatusDb:
    def __init__(self, dsn):
        import sqlite3
        self.conn = sqlite3.connect(dsn)
        self.create_schema()

    def create_schema(self):
        with open(join("sql", "00_schema.sql")) as fd:
            sql = fd.read()
            with self.conn:
                self.conn.executescript(sql)


if __name__ == '__main__':
    arguments = docopt(__doc__)
    sdb = StatusDb(arguments["--output"])
