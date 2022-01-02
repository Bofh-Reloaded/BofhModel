CREATE TABLE schema_version(version INT);
INSERT INTO schema_version(version) VALUES (0);

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
    UNIQUE(address)
);

CREATE UNIQUE INDEX tokens_address_idx ON tokens(address);
CREATE UNIQUE INDEX exchanges_name_idx ON exchanges(name);
CREATE UNIQUE INDEX pools_address_idx ON pools(address);

