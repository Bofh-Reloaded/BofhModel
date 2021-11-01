CREATE TABLE schema_version(version INT);

INSERT INTO schema_version(version) VALUES (0);

CREATE TABLE pools(
    addr TEXT PRIMARY KEY,
    token0 TEXT NOT NULL,
    token1 TEXT NOT NULL,
    baseWeight INT NOT NULL,
    counterWeight INT NOT NULL,
    swapFee INT NOT NULL,
    empty INT NOT NULL
);

CREATE TABLE tokens(
    addr TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE INDEX pool_token0_idx ON pools (token0);
CREATE INDEX pool_token1_idx ON pools (token1);
