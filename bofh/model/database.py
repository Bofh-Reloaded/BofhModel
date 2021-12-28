from functools import cached_property
from logging import getLogger
from sqlite3 import IntegrityError

from attr import dataclass
from docopt import docopt
from glob import glob
from os.path import realpath, dirname, join, exists, basename

schemadir = join(dirname(realpath(__file__)), "schema")


@dataclass
class Exchange:
    id: int
    name: str


@dataclass
class Token:
    id: int
    address: str
    name: str
    is_stabletoken: bool


@dataclass
class Pool:
    id: int
    name: str
    exchange_id: int
    token0_id: int
    token1_id: int


class ModelDB:
    log = getLogger(__name__)

    @staticmethod
    def _split_dsn(db_dsn: str):
        ofs = db_dsn.find("://")
        if ofs<0:
            return "sqlite3", db_dsn
        return db_dsn[0:ofs], db_dsn[ofs+3:]

    def __init__(self, db_dsn):
        self.conn = None
        self.driver_name, self.db_dsn = self._split_dsn(db_dsn)
        self.driver = __import__(self.driver_name)
        self.just_initialized = False

    def open_and_priming(self):
        if not self.exists:
            self.initialize()
        else:
            self.open()
        self.update_schema()

    @property
    def exists(self):
        if not self.conn:
            try:
                self.open()
                curs = self.conn.cursor()
                curs.execute("SELECT * FROM schema_version ORDER BY version DESC LIMIT 1 ")
                return curs.fetchone()[0]
            except:
                return False
        return True

    def __list_schemafiles(self, glob_pattern): # iter[nn, filepath]
        for i in glob(join(schemadir, self.driver_name, glob_pattern)):
            fn = basename(i)
            ofs = fn.find("_")
            if ofs < 1:
                continue
            nns = fn[0:ofs].lstrip("0")
            if not nns: nns = "0"
            yield int(nns), i

    @property
    def most_recent_schema(self):
        files = dict(self.__list_schemafiles("*_schema.sql"))
        return files[max(files)]

    def initialize(self):
        self.open()
        try:
            schemafile = self.most_recent_schema
            self.log.debug("initializing database schema using %s", schemafile)
            with open(schemafile, "r") as fd:
                self.conn.executescript(fd.read())
                self.conn.commit()
        except:
            self.log.exception("error accessing DB")
            raise
        self.just_initialized = True

    def open(self):
        if self.conn is not None:
            return
        self.log.debug("opening database at %s", self.db_dsn)
        self.conn = self.driver.connect(self.db_dsn)

    @property
    def current_schema_version(self):
        try:
            curs = self.conn.cursor()
            curs.execute("SELECT * FROM schema_version ORDER BY version DESC LIMIT 1 ")
            return curs.fetchone()[0]
        except:
            self.log.exception("error accessing DB")
            raise

    @property
    def latest_schema_version(self):
        if not self.migrations:
            return 0
        return max(self.migrations)

    @cached_property
    def migrations(self):
        return dict(self.__list_schemafiles("*_migration.sql"))

    def update_schema(self):
        assert self.conn is not None
        current_version = self.current_schema_version
        self.log.info("current schema version is %r", current_version)
        latest = self.latest_schema_version
        assert current_version <= latest
        if current_version == latest:
            self.log.info("current schema version up to date")
            return
        self.log.info("a new schema version is available. updading %r to %r ...", current_version, latest)
        for i in range(current_version+1, latest+1):
            try:
                mfile = self.migrations[i]
                self.log.debug("using %s for upgrading to schema version %r...", mfile, i)
                with open(mfile, "r") as fd:
                    self.conn.executescript(fd.read())
                self.conn.cursor().execute("INSERT INTO schema_version(version) VALUES (%r)" % i)
                self.conn.commit()
            except KeyError:
                self.log.error("no migration file found for schema version %r. bailing out now", i)
                return
        self.log.info("successfully bumped schema version up to version %r", latest)

    def __enter__(self):
        assert self.conn is not None
        return ScopedCursor(self.conn)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.conn.rollback()
        else:
            self.conn.commit()


class ScopedCursor:
    BLOCK_FETCH_SIZE=1000

    def __init__(self, conn):
        self.conn = conn
        self.curs = self.conn.cursor()
        self.curs.arraysize = self.BLOCK_FETCH_SIZE

    def execute(self, *a, **ka):
        self.curs.execute(*a, **ka)
        return self

    def get_int(self):
        return self.curs.fetchone()[0]

    def add_token(self, address, name=None, ignore_duplicates=False):
        assert self.conn is not None
        try:
            self.execute("INSERT INTO tokens (address, name) VALUES (?, ?)", (address, name))
            self.execute("SELECT last_insert_rowid()")
        except IntegrityError:
            # already existing
            if not ignore_duplicates:
                raise
            self.execute("SELECT id FROM tokens WHERE address = ?", (address,))
        return self.get_int()

    def add_exchange(self, name=None, ignore_duplicates=False):
        assert self.conn is not None
        try:
            self.execute("INSERT INTO exchanges (name) VALUES (?)", (name,))
            self.execute("SELECT last_insert_rowid()")
        except IntegrityError:
            # already existing
            if not ignore_duplicates:
                raise
            self.execute("SELECT id FROM exchanges WHERE name = ?", (name,))
        return self.get_int()

    def add_swap(self, address, exchange_id, token0_id, token1_id, ignore_duplicates=False):
        assert self.conn is not None
        try:
            self.execute("INSERT INTO pools (address, exchange_id, token0_id, token1_id) VALUES (?, ?, ?, ?)",
                         (address, exchange_id, token0_id, token1_id))
            self.execute("SELECT last_insert_rowid()")
        except IntegrityError:
            # already existing
            if not ignore_duplicates:
                raise
            self.execute("SELECT id FROM pools WHERE address = ?", (address,))
        return self.get_int()

    def list_exchanges(self):
        assert self.conn is not None
        self.execute("SELECT id,name FROM exchanges")
        while True:
            seq = self.curs.fetchmany()
            if not seq:
                return
            for i in seq:
                yield i

    def list_tokens(self):
        assert self.conn is not None
        self.execute("SELECT id,COALESCE(name, ''),address,is_stabletoken FROM tokens")
            # note: using COALESCE() bc many tokens simply does not have, nor will have, a known name
            # The token name is just used for logging purposes though. It's just a human label attribute.
        while True:
            seq = self.curs.fetchmany()
            if not seq:
                return
            for i in seq:
                yield i

    def list_pools(self):
        assert self.conn is not None
        self.execute("SELECT id,address,exchange_id,token0_id,token1_id FROM pools")
        while True:
            seq = self.curs.fetchmany()
            if not seq:
                return
            for i in seq:
                yield i
