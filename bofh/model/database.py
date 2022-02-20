from functools import cached_property
from sqlite3 import IntegrityError
from threading import Lock
from time import time
from typing import List

from attr import dataclass
from glob import glob
from os.path import realpath, dirname, join, basename

from bofh.model.modules.loggers import Loggers

schemadir = join(dirname(realpath(__file__)), "schema")


@dataclass
class Exchange:
    id: int
    name: str
    router_address: str = None


@dataclass
class Token:
    id: int
    name: str
    address: str
    is_stabletoken: bool
    decimals: int
    symbol: str = None
    disabled: int = 0

    def get_symbol(self):
        if self.symbol: return self.symbol
        return norm_address(self.address)[0:8]

    def fromWei(self, weis):
        return weis / (10**self.decimals)

    def toWei(self, amount):
        return amount * (10**self.decimals)


@dataclass
class Pool:
    id: int
    address: str
    exchange_id: int
    token0_id: int
    token1_id: int


@dataclass
class InterventionStep:
    pool_id: int
    pool_addr: str
    reserve0: int
    reserve1: int
    tokenIn_addr: str
    tokenOut_addr: str
    tokenIn_id: str
    tokenOut_id: str
    amountIn: int
    feePPM: int
    amountOut: int

@dataclass
class Intervention:
    origin: str
    origin_tx: str = ""
    origin_ts: int = 0
    amountIn: int = 0
    amountOut: int = 0
    path_id: int = 0
    contract: str = None
    calldata: str = None
    blockNr: int = 0
    tag: int = None
    steps: List[InterventionStep] = []

    @property
    def yieldPercent(self):
        return 100*((self.amountOut / self.amountIn)-1)


class ModelDB:
    log = Loggers.database

    @staticmethod
    def _split_dsn(db_dsn: str):
        ofs = db_dsn.find("://")
        if ofs<0:
            return "sqlite3", db_dsn
        return db_dsn[0:ofs], db_dsn[ofs+3:]

    def __init__(self, schema_name, cursor_factory, db_dsn):
        self.schema_name = schema_name
        self.cursor_factory = cursor_factory
        self.conn = None
        self.driver_name, self.db_dsn = self._split_dsn(db_dsn)
        self.driver = __import__(self.driver_name)
        self.just_initialized = False
        self.lock = Lock()

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
                return curs.fetchone()[0] is not None
            except:
                return False
        return True

    def __list_schemafiles(self, glob_pattern): # iter[nn, filepath]
        for i in glob(join(schemadir, self.schema_name, self.driver_name, glob_pattern)):
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
        self.conn = self.driver.connect(self.db_dsn, check_same_thread=False)

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
        self.log.debug("current schema version is %r", current_version)
        latest = self.latest_schema_version
        assert current_version <= latest
        if current_version == latest:
            self.log.debug("current schema version up to date")
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
        return self.cursor()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.conn.rollback()
        else:
            self.conn.commit()

    def cursor(self):
        assert self.conn is not None
        return self.cursor_factory(self, self.conn)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()


class BasicScopedCursor:
    BLOCK_FETCH_SIZE=1000

    def __init__(self, parent, conn):
        self.lock = parent.lock
        self.conn = conn
        self.curs = self.conn.cursor()
        self.curs.arraysize = self.BLOCK_FETCH_SIZE

    def execute(self, *a, **ka):
        with self.lock:
            self.curs.execute(*a, **ka)
            return self

    def executemany(self, *a, **ka):
        with self.lock:
            self.curs.executemany(*a, **ka)
            return self

    def get_int(self):
        with self.lock:
            return self.curs.fetchone()[0]

    def get_one(self):
        with self.lock:
            return self.curs.fetchone()[0]

    def get(self):
        with self.lock:
            return self.curs.fetchone()

    def get_all(self):
        while True:
            with self.lock:
                seq = self.curs.fetchmany()
                if not seq:
                    return
                for i in seq:
                    yield i

def norm_address(a: str):
    return str(a).lower()

class StatusScopedCursor(BasicScopedCursor):
    MAX_TOKEN_NAME_LEN = 64
    MAX_TOKEN_SYMBOL_LEN = 64
    META_TABLE = "status_meta"

    def add_token(self, address, name=None, ignore_duplicates=False):
        assert self.conn is not None
        try:
            self.execute("INSERT INTO tokens (address, name) VALUES (?, ?)", (norm_address(address), name))
            self.execute("SELECT last_insert_rowid()")
        except IntegrityError:
            # already existing
            if not ignore_duplicates:
                raise
            self.execute("SELECT id FROM tokens WHERE address = ?", (norm_address(address),))
        return self.get_int()

    def add_exchange(self, router_address, name=None, ignore_duplicates=False):
        assert self.conn is not None
        try:
            self.execute("INSERT INTO exchanges (router_address, name) VALUES (?, ?)", (norm_address(router_address), name,))
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
                         (norm_address(address), exchange_id, token0_id, token1_id))
            self.execute("SELECT last_insert_rowid()")
        except IntegrityError:
            # already existing
            if not ignore_duplicates:
                raise
            self.execute("SELECT id FROM pools WHERE address = ?", (norm_address(address),))
        return self.get_int()

    def list_exchanges(self):
        assert self.conn is not None
        self.execute("SELECT id,router_address,name FROM exchanges")
        while True:
            seq = self.curs.fetchmany()
            if not seq:
                return
            for i in seq:
                yield i

    def count_tokens(self):
        return self.execute("SELECT COUNT(1) FROM tokens WHERE NOT disabled").get_int()

    def list_tokens(self):
        assert self.conn is not None
        self.execute("SELECT id"
                     ", address"
                     ", SUBSTR(COALESCE(name, ''), 0, ?)"
                     ", SUBSTR(COALESCE(symbol, ''), 0, ?)"
                     ", decimals"
                     ", is_stabletoken FROM tokens WHERE NOT disabled", (self.MAX_TOKEN_NAME_LEN, self.MAX_TOKEN_SYMBOL_LEN))
            # note: using COALESCE() bc many tokens simply does not have, nor will have, a known name
            # The token name is just used for logging purposes though. It's just a human label attribute.
        while True:
            seq = self.curs.fetchmany()
            if not seq:
                return
            for i in seq:
                yield i

    def count_pools(self):
        return self.execute("SELECT COUNT(1) FROM pools").get_int()

    def list_pools(self):
        assert self.conn is not None
        self.execute("SELECT id,address,exchange_id,token0_id,token1_id FROM pools")
        while True:
            seq = self.curs.fetchmany()
            if not seq:
                return
            for i in seq:
                yield i

    RAISE_ERROR=object()

    def get_meta(self, key, default=RAISE_ERROR, cast=None):
        try:
            v = self.execute("SELECT value FROM %s WHERE key = ?" % self.META_TABLE, (key,)).get_one()
            if cast:
                v = cast(v)
            return v
        except:
            if default is self.RAISE_ERROR:
                raise KeyError("missing key in %s: %s" % (self.META_TABLE, key))
            return default

    def set_meta(self, key, value, cast=str):
        try:
            value = cast(value)
            self.execute("INSERT INTO %s (key, value) VALUES (?, ?)" % self.META_TABLE, (key, value))
        except IntegrityError:
            self.execute("UPDATE %s SET value = ? WHERE key = ?" % self.META_TABLE, (value, key))

    def update_latest_blocknr(self, blockNr: int):
        key = "reserves_block_number"
        self.set_meta(key, blockNr)

    def get_latest_blocknr(self) -> int:
        key = "reserves_block_number"
        return self.get_meta(key, cast=int, default=0)

    reserves_block_number = property(get_latest_blocknr, update_latest_blocknr)

    def add_pool_reserve(self, pool_id, reserve0, reserve1):
        assert self.conn is not None
        if not isinstance(reserve0, str): reserve0 = str(reserve0)
        if not isinstance(reserve1, str): reserve1 = str(reserve1)
        try:
            self.execute("INSERT INTO pool_reserves (id, reserve0, reserve1) VALUES (?, ?, ?)", (pool_id, reserve0, reserve1))
            self.execute("SELECT last_insert_rowid()")
        except IntegrityError:
            # already existing
            self.execute("UPDATE pool_reserves SET reserve0 = ?, reserve1 = ? WHERE id = ?", (reserve0, reserve1, pool_id))

    def update_pool_reserves_batch(self, tuples):
        self.executemany("UPDATE pool_reserves SET reserve0 = ?, reserve1 = ? WHERE id = ?", tuples)

    def intervention_is_in_mute_cache(self, o: Intervention, cache_deadline, max_size=0):
        ts_of_largest_collection = None
        path_id = str(o.path_id)
        if max_size:
            ts_of_largest_collection_sql = "SELECT origin_ts FROM interventions ORDER BY origin_ts DESC LIMIT 1 OFFSET %u" % max_size
            try:
                ts_of_largest_collection = self.execute(ts_of_largest_collection_sql).get_int()
            except:
                pass
        check_colliding_sql = "SELECT COUNT(1) FROM interventions WHERE path_id = ? AND origin_ts >= ?"
        if ts_of_largest_collection:
            args = (path_id, ts_of_largest_collection)
        else:
            args = (path_id, int(time() - cache_deadline))
        return self.execute(check_colliding_sql, args).get_int() > 0

    def add_intervention(self, o: Intervention):
        path_id = str(o.path_id)
        args = (o.origin, o.blockNr, o.origin_tx, int(o.origin_ts), str(o.amountIn), str(o.amountOut), float(o.amountOut/o.amountIn), path_id, len(o.steps), o.contract, o.calldata)
        self.execute("INSERT INTO interventions (origin, blockNr, origin_tx, origin_ts, amountIn, amountOut, yieldRatio, path_id, path_size, contract, calldata) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", args)
        o.tag = self.execute("SELECT last_insert_rowid()").get_int()
        def steps_iter():
            for step in o.steps:
                yield (o.tag, step.pool_id, norm_address(step.pool_addr), str(step.reserve0), str(step.reserve1),
                       norm_address(step.tokenIn_addr), norm_address(step.tokenOut_addr), step.tokenIn_id, step.tokenOut_id,
                       str(step.amountIn), step.feePPM, str(step.amountOut))
        self.executemany("INSERT INTO intervention_steps (fk_intervention, pool_id, pool_addr, reserve0, reserve1, "
                         "tokenIn_addr, tokenOut_addr, tokenIn_id, tokenOut_id, amountIn, feePPM, amountOut) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", steps_iter())

    def add_unknown_pool(self, address):
        try:
            self.execute("INSERT INTO unknown_pools (address) VALUES (?)", (norm_address(address),))
            return True
        except IntegrityError:
            return False

    def set_unknown_pool_factory(self, pool, address):
        self.execute("UPDATE unknown_pools SET factory = ? WHERE address = ?", (norm_address(address), pool))

    def set_unknown_pool_disabled(self, pool, disabled):
        self.execute("UPDATE unknown_pools SET disabled = ? WHERE address = ?", (disabled, pool))

    def get_intervention(self, id) -> Intervention:
        id, origin, origin_tx, origin_ts, \
        blockNr, amountIn, amountOut, yieldRatio, \
        path_id, contract, calldata  = \
        self.execute("SELECT id, origin, origin_tx, origin_ts, "
                                "blockNr, amountIn, amountOut, yieldRatio, "
                                "path_id, contract, calldata FROM interventions WHERE id = ?", (id,)).get()
        steps = []
        i = Intervention(tag=id, origin=origin, origin_tx=origin_tx, origin_ts=origin_ts, blockNr=blockNr
                         , amountIn=int(amountIn), amountOut=int(amountOut)
                         , path_id=int(path_id), contract=contract, calldata=calldata, steps=steps)
        for r in self.execute("SELECT pool_id, pool_addr, reserve0, reserve1"
                              ", tokenIn_addr, tokenOut_addr, tokenIn_id, tokenOut_id"
                              ",  amountIn, feePPM, amountOut "
                              "FROM intervention_steps WHERE fk_intervention = ? ORDER BY id ASC", (id,)).get_all():
            pool_id, pool_addr, reserve0, reserve1, \
            tokenIn_addr, tokenOut_addr, tokenIn_id, tokenOut_id, \
            amountIn, feePPM, amountOut = r
            steps.append(InterventionStep(pool_id=pool_id
                                          , pool_addr=pool_addr
                                          , reserve0=int(reserve0)
                                          , reserve1=int(reserve1)
                                          , tokenIn_addr=tokenIn_addr
                                          , tokenOut_addr=tokenOut_addr
                                          , tokenIn_id=tokenIn_id
                                          , tokenOut_id=tokenOut_id
                                          , amountIn=int(amountIn)
                                          , amountOut=int(amountOut)
                                          , feePPM=feePPM))
        return i

    def get_token(self, id=None, address=None):
        assert (id, address) != (None, None)
        if address:
            sql = "SELECT * FROM tokens WHERE address = ?"
            args = [norm_address(address)]
        elif id:
            sql = "SELECT * FROM tokens WHERE id = ?"
            args = [id]
        r = self.execute(sql, args).get()
        return Token(*r)

    def get_pool(self, id=None, address=None):
        assert (id, address) != (None, None)
        if address:
            sql = "SELECT * FROM pools WHERE address = ?"
            args = [norm_address(address)]
        elif id:
            sql = "SELECT * FROM pools WHERE id = ?"
            args = [id]
        r = self.execute(sql, args).get()
        return Pool(*r)

    def get_exchange(self, id):
        sql = "SELECT id, name FROM exchanges WHERE id = ?"
        args = [id]
        r = self.execute(sql, args).get()
        return Exchange(*r)
