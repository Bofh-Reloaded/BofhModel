CREATE TABLE schema_version(version INT);
INSERT INTO schema_version(version) VALUES (2);

-- List of changes:
-- 00 initial schema
-- 01 no changes
-- 02 add pools.reserve0, reserve1


-- TOKENS table
-- address) is blockchain address in text representation, including leading "0x"
-- name) for those tokens that do have a widely known name (WBNB, ETH, USDC, etc), this is only used for logging purposes
-- is_stabletoken) set to >0 to give hints to the path finder model. Stabletokens will be used as second course of
--                 of action in order to find a path back to the home token.

CREATE TABLE tokens(
    id INTEGER PRIMARY KEY,
    address TEXT NOT NULL,
    name TEXT,
    is_stabletoken INTEGER NOT NULL DEFAULT 0
);


-- EXCHANGES table

CREATE TABLE exchanges(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);


-- POOLS table. Each entry represents a known swap
-- address) is blockchain address in text representation, including leading "0x"
-- exchange_id, token0_id, token1_id) are foreign keys, self explanatory
--                                    IMPORTANT. Runtime should make sure that there are no two entries
--                                    sharing the same exchange_id, token0_id and token1_id, and this must be
--                                    held true even after swapping the two tokens. (Swaps are bidirectional)
-- reserve0, reserve1) Textual representation of the uint256 representing the balance of stored reserve for
--                     token0 and token1 in the liquidity pool.
-- updated) An external should take care to set updated=unix_time() (or updated=strftime('%s', 'now') in SQLite lingo)
--          in order to mark those records that need to be reread by the agent.

CREATE TABLE pools(
    id INTEGER PRIMARY KEY,
    address TEXT NOT NULL,
    exchange_id INTEGER NOT NULL,
    token0_id INTEGER NOT NULL,
    token1_id INTEGER NOT NULL,
    reserve0 TEXT DEFAULT NULL, -- uint256 stored as TEXT representation
    reserve1 TEXT DEFAULT NULL, -- uint256 stored as TEXT representation
    updated INTEGER NOT NULL DEFAULT 0
);


-- INDEXES and CONSTRAINTS

CREATE UNIQUE INDEX tokens_address_idx ON tokens(address);
CREATE UNIQUE INDEX exchanges_name_idx ON exchanges(name);
CREATE UNIQUE INDEX pools_address_idx ON pools(address);
CREATE INDEX pools_updated_idx ON pools(updated);

