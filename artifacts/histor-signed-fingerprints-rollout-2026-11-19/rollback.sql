-- Back to a schema the image before migration 025 accepts. Sets taken from signed statements are marked
-- withdrawn (kept as history), their pointer rows removed; then the two columns and the schema row go.
UPDATE declared_toolsets SET withdrawn_at = to_char(now() at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
  WHERE source = 'signed' AND withdrawn_at IS NULL;
DELETE FROM declaration_urls WHERE pointer IS NOT NULL;
ALTER TABLE declaration_urls DROP COLUMN IF EXISTS pointer;
ALTER TABLE declaration_urls DROP COLUMN IF EXISTS statement;
DELETE FROM schema_migrations WHERE version = 25;
