CREATE TABLE IF NOT EXISTS profile_frameworks_custom (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL DEFAULT 'default',
    name        TEXT NOT NULL,
    catalog     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_profile_frameworks_custom_tenant
    ON profile_frameworks_custom (tenant_id);
