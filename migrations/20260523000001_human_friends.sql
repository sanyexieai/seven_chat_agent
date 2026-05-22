-- Human friend session & invite tables
CREATE TABLE IF NOT EXISTS human_sessions (
    friend_id       TEXT PRIMARY KEY REFERENCES friends(id) ON DELETE CASCADE,
    channel         TEXT NOT NULL,
    endpoint        TEXT,
    auth_token_ref  TEXT,
    presence        TEXT NOT NULL DEFAULT 'offline',
    typing_until    TEXT,
    last_seen_at    TEXT,
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS invites (
    id              TEXT PRIMARY KEY,
    friend_id       TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    code            TEXT NOT NULL UNIQUE,
    expires_at      TEXT,
    used_at         TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_invites_friend ON invites(friend_id);
