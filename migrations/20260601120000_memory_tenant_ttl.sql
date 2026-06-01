-- 多租户占位 + 临时记忆 TTL + 按租户隔离记忆
CREATE TABLE IF NOT EXISTS tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT OR IGNORE INTO tenants (id, name) VALUES ('default', 'Default');

ALTER TABLE memories ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE memories ADD COLUMN expires_at TEXT;

CREATE INDEX IF NOT EXISTS idx_memories_tenant_owner
    ON memories(tenant_id, owner_friend_id);

CREATE INDEX IF NOT EXISTS idx_memories_expires
    ON memories(expires_at)
    WHERE expires_at IS NOT NULL;

-- 助理全局策略按租户一行（id = tenant_id）；保留 global 行兼容旧数据
INSERT OR IGNORE INTO assistant_global_settings (id, settings, updated_at)
SELECT 'default', settings, updated_at
FROM assistant_global_settings
WHERE id = 'global';
