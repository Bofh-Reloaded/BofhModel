CREATE TABLE schema_version(version INT);
INSERT INTO schema_version(version) VALUES (0);

CREATE TABLE unknown_pools (
    address TEXT NOT NULL PRIMARY KEY,
    factory TEXT DEFAULT NULL
);

