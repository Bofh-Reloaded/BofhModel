
-- add reserve columns to pairs table: there is no native uint256 datatype. We are storing it as text
-- I'll consider changing this to BLOB later, but there is no real advantage. It's slightly more compact
-- but one would lose the ability to see the record in human readable form, so...


ALTER TABLE pools ADD COLUMN reserve0 TEXT DEFAULT NULL;
ALTER TABLE pools ADD COLUMN reserve1 TEXT DEFAULT NULL;
ALTER TABLE pools ADD COLUMN updated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tokens ADD COLUMN is_stabletoken INTEGER NOT NULL DEFAULT 0;
CREATE INDEX pools_updated_idx ON pools(updated);


