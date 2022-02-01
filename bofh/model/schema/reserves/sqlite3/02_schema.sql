CREATE TABLE schema_version(version INT);
INSERT INTO schema_version(version) VALUES (2);

CREATE TABLE swap_logs(
    id INTEGER PRIMARY KEY,
    block_nr INTEGER NOT NULL,
    json_data TEXT NOT NULL,
    pool INTEGER NOT NULL,
    tokenIn INTEGER NOT NULL,
    tokenOut INTEGER NOT NULL,
    poolAddr TEXT NOT NULL,
    tokenInAddr TEXT NOT NULL,
    tokenOutAddr TEXT NOT NULL,
    balanceIn TEXT NOT NULL,
    balanceOut TEXT NOT NULL,
    reserveInBefore TEXT NOT NULL,
    reserveOutBefore TEXT NOT NULL
);

CREATE TABLE pool_reserves(
    id INTEGER PRIMARY KEY,
    pool INTEGER NOT NULL,
    reserve0 TEXT NOT NULL,
    reserve1 TEXT NOT NULL
);

CREATE INDEX swap_logs_block_nr_idx ON swap_logs(block_nr);
CREATE UNIQUE INDEX pool_reserves_pool_idx ON pool_reserves(pool);
-- we seem to perform a lot of counting and joining upon these columns. I'm adding two indexes:
CREATE INDEX swap_logs_tokenIn_idx ON swap_logs(tokenIn);
CREATE INDEX swap_logs_tokenOut_idx ON swap_logs(tokenOut);

CREATE TABLE reserves_meta (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL
);
