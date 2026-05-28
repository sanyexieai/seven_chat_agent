-- 助理全局策略（单例行 id=global）
CREATE TABLE IF NOT EXISTS assistant_global_settings (
    id          TEXT PRIMARY KEY,
    settings    TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT OR IGNORE INTO assistant_global_settings (id, settings)
VALUES ('global', '{}');
