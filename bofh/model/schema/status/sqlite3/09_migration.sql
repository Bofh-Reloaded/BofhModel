ALTER TABLE exchanges ADD COLUMN fees_ppm INT NOT NULL DEFAULT 2500;
ALTER TABLE tokens ADD COLUMN fees_ppm INT NOT NULL DEFAULT 0;
ALTER TABLE pools ADD COLUMN fees_ppm INT NOT NULL DEFAULT 0;

