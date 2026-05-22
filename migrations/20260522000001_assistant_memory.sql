-- Assistant memory & skills tables
CREATE TABLE IF NOT EXISTS memories (
    id              TEXT PRIMARY KEY,
    owner_friend_id TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    content         TEXT NOT NULL,
    source_message_id       TEXT,
    weight          REAL NOT NULL DEFAULT 0.5,
    pinned          INTEGER NOT NULL DEFAULT 0,
    last_used_at    TEXT,
    decay_score     REAL NOT NULL DEFAULT 1.0,
    embedding       BLOB,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_memories_owner ON memories(owner_friend_id, kind);
CREATE INDEX IF NOT EXISTS idx_memories_weight ON memories(owner_friend_id, weight DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    kind UNINDEXED,
    content='memories',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, kind) VALUES (new.rowid, new.content, new.kind);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, kind) VALUES('delete', old.rowid, old.content, old.kind);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, kind) VALUES('delete', old.rowid, old.content, old.kind);
    INSERT INTO memories_fts(rowid, content, kind) VALUES (new.rowid, new.content, new.kind);
END;

CREATE TABLE IF NOT EXISTS skills (
    id              TEXT PRIMARY KEY,
    owner_friend_id TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    path            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    triggers        TEXT NOT NULL DEFAULT '[]',
    requires_toolsets       TEXT NOT NULL DEFAULT '[]',
    platforms       TEXT NOT NULL DEFAULT '[]',
    trust_level     TEXT NOT NULL DEFAULT 'agent_created',
    guard_report    TEXT NOT NULL DEFAULT '{}',
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(owner_friend_id, name)
);

CREATE INDEX IF NOT EXISTS idx_skills_owner ON skills(owner_friend_id);

CREATE TABLE IF NOT EXISTS skill_runs (
    id              TEXT PRIMARY KEY,
    skill_id        TEXT REFERENCES skills(id) ON DELETE CASCADE,
    candidate_name  TEXT,
    owner_friend_id TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    message_id      TEXT REFERENCES messages(id) ON DELETE SET NULL,
    succeeded       INTEGER NOT NULL,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    patch_applied   INTEGER NOT NULL DEFAULT 0,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_skill_runs_owner ON skill_runs(owner_friend_id, candidate_name);

CREATE TABLE IF NOT EXISTS reflections (
    id              TEXT PRIMARY KEY,
    owner_friend_id TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    turn_id         TEXT NOT NULL,
    score           REAL NOT NULL DEFAULT 0,
    summary         TEXT NOT NULL,
    lessons         TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
