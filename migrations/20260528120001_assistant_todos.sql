CREATE TABLE IF NOT EXISTS assistant_todos (
    id              TEXT PRIMARY KEY,
    owner_friend_id TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    detail          TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    priority        INTEGER NOT NULL DEFAULT 1,
    source_turn_id  TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_assistant_todos_owner_status
ON assistant_todos(owner_friend_id, status, priority, updated_at);

