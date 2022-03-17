-- drop columns pools.fees_ppm tokens.fees_ppm, recreate it as DEFAULT NULL
ALTER TABLE tokens RENAME TO tokens_old;
CREATE TABLE tokens(
    id INTEGER PRIMARY KEY,
    name TEXT,
    address TEXT NOT NULL,
    is_stabletoken INTEGER NOT NULL DEFAULT 0,
    decimals INT DEFAULT NULL,
    symbol TEXT DEFAULT NULL,
    disabled INT NOT NULL DEFAULT 0
);
INSERT INTO tokens (id, name, address, is_stabletoken, decimals, symbol, disabled)
    SELECT id, name, address, is_stabletoken, decimals, symbol, disabled FROM tokens_old;
DROP TABLE tokens_old;
ALTER TABLE tokens ADD COLUMN fees_ppm INT DEFAULT NULL;


ALTER TABLE pools RENAME TO pools_old;
CREATE TABLE pools(
    id INTEGER PRIMARY KEY,
    address TEXT NOT NULL,
    exchange_id INTEGER NOT NULL,
    token0_id INTEGER NOT NULL,
    token1_id INTEGER NOT NULL,
    disabled INT NOT NULL DEFAULT 0
);
INSERT INTO pools (id, address, exchange_id, token0_id, token1_id, disabled)
    SELECT id, address, exchange_id, token0_id, token1_id, disabled FROM pools_old;
DROP TABLE pools_old;
ALTER TABLE pools ADD COLUMN fees_ppm INT DEFAULT NULL;

