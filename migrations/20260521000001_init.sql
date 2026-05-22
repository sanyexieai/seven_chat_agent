-- Initial schema for honeycomb
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS providers (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    base_url        TEXT NOT NULL,
    default_model   TEXT,
    capabilities    TEXT NOT NULL DEFAULT '{}',
    price           TEXT NOT NULL DEFAULT '{}',
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS provider_keys (
    id              TEXT PRIMARY KEY,
    provider_id     TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    label           TEXT NOT NULL,
    secret_ref      TEXT NOT NULL,
    rpm_limit       INTEGER,
    tpm_limit       INTEGER,
    monthly_budget_usd      REAL,
    current_spent_usd       REAL NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_provider_keys_provider ON provider_keys(provider_id);

CREATE TABLE IF NOT EXISTS friends (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    avatar          TEXT,
    system_prompt   TEXT NOT NULL DEFAULT '',
    personality     TEXT,
    focus_tags      TEXT NOT NULL DEFAULT '[]',
    backend_kind    TEXT NOT NULL,
    backend_config  TEXT NOT NULL DEFAULT '{}',
    judge_provider_ref      TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    is_builtin      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_friends_kind ON friends(backend_kind);

CREATE TABLE IF NOT EXISTS groups (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    avatar          TEXT,
    settings        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id        TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    friend_id       TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'member',
    joined_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (group_id, friend_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    title           TEXT,
    last_message_at TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(kind, target_id)
);

CREATE INDEX IF NOT EXISTS idx_conversations_target ON conversations(kind, target_id);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    turn_id         TEXT NOT NULL,
    parent_id       TEXT,
    sender_kind     TEXT NOT NULL,
    sender_id       TEXT NOT NULL,
    sender_name     TEXT NOT NULL,
    content         TEXT NOT NULL DEFAULT '',
    mentions        TEXT NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'done',
    seen_by         TEXT NOT NULL DEFAULT '[]',
    model_used      TEXT,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_turn ON messages(turn_id);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    sender_name,
    content='messages',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, sender_name) VALUES (new.rowid, new.content, new.sender_name);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, sender_name) VALUES('delete', old.rowid, old.content, old.sender_name);
END;

CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, sender_name) VALUES('delete', old.rowid, old.content, old.sender_name);
    INSERT INTO messages_fts(rowid, content, sender_name) VALUES (new.rowid, new.content, new.sender_name);
END;

CREATE TABLE IF NOT EXISTS judgments (
    id              TEXT PRIMARY KEY,
    message_id      TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    friend_id       TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    should_reply    INTEGER NOT NULL,
    confidence      REAL NOT NULL,
    reason          TEXT,
    suggested_delay_ms      INTEGER NOT NULL DEFAULT 0,
    latency_ms      INTEGER,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_judgments_message ON judgments(message_id);
