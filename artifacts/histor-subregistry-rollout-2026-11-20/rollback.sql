-- Back to a schema the image before migration 026 accepts: the copy of registry entries and its bookkeeping go.
-- Nothing else refers to them (no label, no log leaf, no observation).
DROP TABLE IF EXISTS registry_entries;
DELETE FROM meta WHERE key IN ('subregistry_checkpoint', 'subregistry_full_at', 'subregistry_allow_hash', 'subregistry_last_sync');
DELETE FROM schema_migrations WHERE version = 26;
