CREATE TABLE schema_version(version INT);
INSERT INTO schema_version(version) VALUES (2);

-- List of changes:
-- 00 initial schema
-- 01 no changes
-- 02 add pools.reserve0, reserve1

CREATE TABLE tokens(
    id INTEGER PRIMARY KEY,
    address TEXT NOT NULL,
    name TEXT,
    UNIQUE(address)
);

CREATE TABLE exchanges(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE pools(
    id INTEGER PRIMARY KEY,
    address TEXT NOT NULL,
    exchange_id INTEGER NOT NULL,
    token0_id INTEGER NOT NULL,
    token1_id INTEGER NOT NULL,
    reserve0 TEXT DEFAULT NULL, -- uint256 stored as TEXT representation
    reserve1 TEXT DEFAULT NULL, -- uint256 stored as TEXT representation
    UNIQUE(address)
);

CREATE UNIQUE INDEX tokens_address_idx ON tokens(address);
CREATE UNIQUE INDEX exchanges_name_idx ON exchanges(name);
CREATE UNIQUE INDEX pools_address_idx ON pools(address);
