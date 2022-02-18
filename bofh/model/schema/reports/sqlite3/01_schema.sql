CREATE TABLE schema_version(version INT);
INSERT INTO schema_version(version) VALUES (1);

CREATE TABLE unknown_pools (
    address TEXT NOT NULL PRIMARY KEY,
    factory TEXT DEFAULT NULL,
    disabled INT NOT NULL DEFAULT 0
);

