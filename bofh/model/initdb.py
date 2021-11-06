"""Create or update database schema.

Usage: bofh.model.initdb [options] <dbfile>

Options:
  -h --help
  -u, --update        update to the most recent schema version, if one is available
  -d, --driver=<name> sqlapi driver name [default: sqlite3]
  -v, --verbose       debug output
"""
from logging import basicConfig

from docopt import docopt

from bofh.model.database import ModelDB


def main():
    arguments = docopt(__doc__)
    basicConfig(level=arguments["--verbose"] and "DEBUG" or "INFO")
    db = ModelDB(fpath=arguments["<dbfile>"], driver_name=arguments["--driver"])
    if not db.exists:
        db.initialize()
    else:
        db.open()
    if arguments["--update"] or db.just_initialized:
        db.update_schema()


if __name__ == '__main__':
    main()
