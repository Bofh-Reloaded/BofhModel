CREATE TABLE schema_version(version INT);
INSERT INTO schema_version(version) VALUES (0);

CREATE TABLE attacks (
    id INTEGER PRIMARY KEY,
    origin TEXT NOT NULL DEFAULT 'pred', -- or 'scan'
    origin_tx TEXT DEFAULT NULL,
    origin_ts INTEGER NOT NULL,
    blockNr INT NOT NULL,
    amountIn TEXT NOT NULL,
    amountOut TEXT NOT NULL,
    yieldRatio REAL NOT NULL,
    path_id TEXT NOT NULL,
    path_size INTEGER NOT NULL,
    contract TEXT NOT NULL,
    calldata TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE attack_steps (
    id INTEGER PRIMARY KEY,
    fk_attack INTEGER NOT NULL,
    pool_id INTEGER NOT NULL,
    pool_addr TEXT NOT NULL,
    reserve0 TEXT NOT NULL,
    reserve1 TEXT NOT NULL,
    tokenIn_addr TEXT NOT NULL,
    tokenOut_addr TEXT NOT NULL,
    tokenIn_id INTEGER NOT NULL,
    tokenOut_id INTEGER NOT NULL,
    amountIn TEXT NOT NULL,
    feePPM INT NOT NULL,
    amountOut TEXT NOT NULL
);

CREATE TABLE attack_outcomes (
    id INTEGER PRIMARY KEY,
    fk_attack INTEGER NOT NULL,
    ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    blockNr INT NOT NULL,
    outcome TEXT NOT NULL, -- ok, failed, error
    amountOut TEXT DEFAULT NULL,
    yieldRatio REAL NOT NULL,
    contract TEXT NOT NULL,
    calldata TEXT NOT NULL
);



CREATE INDEX attack_path_id_idx ON attacks(path_id);
CREATE INDEX attack_origin_ts_idx ON attacks(origin_ts);
CREATE INDEX attack_steps_fk_idx ON attack_steps(fk_attack);
CREATE INDEX attack_outcomes_fk_idx ON attack_outcomes(fk_attack);
