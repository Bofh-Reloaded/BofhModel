CREATE INDEX pools_token0_id_idx ON pools(token0_id);
CREATE INDEX pools_token1_id_idx ON pools(token1_id);
ALTER TABLE tokens ADD COLUMN decimals INT DEFAULT NULL;
ALTER TABLE tokens ADD COLUMN symbol TEXT DEFAULT NULL;
ALTER TABLE tokens ADD COLUMN disabled INT NOT NULL DEFAULT 0;
