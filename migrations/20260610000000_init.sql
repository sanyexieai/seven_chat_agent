-- Consolidated init schema (squashed from migrations through 20260609100000)
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
, slug TEXT);

CREATE TABLE "providers" (
    tenant_id       TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id),
    id              TEXT NOT NULL,
    kind            TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    base_url        TEXT NOT NULL,
    default_model   TEXT,
    capabilities    TEXT NOT NULL DEFAULT '{}',
    price           TEXT NOT NULL DEFAULT '{}',
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE "provider_keys" (
    id                      TEXT PRIMARY KEY,
    tenant_id               TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id),
    provider_id             TEXT NOT NULL,
    label                   TEXT NOT NULL,
    secret_ref              TEXT NOT NULL,
    rpm_limit               INTEGER,
    tpm_limit               INTEGER,
    monthly_budget_usd      REAL,
    current_spent_usd       REAL NOT NULL DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'active',
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (tenant_id, provider_id) REFERENCES providers(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE friends (
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
, judge_override TEXT, active_workspace_id TEXT REFERENCES workspaces(id), tenant_id TEXT NOT NULL DEFAULT 'default');

CREATE TABLE groups (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    avatar          TEXT,
    settings        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
, tenant_id TEXT NOT NULL DEFAULT 'default');

CREATE TABLE group_members (
    group_id        TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    friend_id       TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'member',
    joined_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), judge_override TEXT,
    PRIMARY KEY (group_id, friend_id)
);

CREATE TABLE conversations (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    title           TEXT,
    last_message_at TEXT,
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    scope_user_id   TEXT REFERENCES users(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE messages (
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
, content_blocks TEXT, on_behalf_of INTEGER NOT NULL DEFAULT 0, workspace_id TEXT, attachments TEXT);

CREATE TABLE memories (
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
, tier TEXT NOT NULL DEFAULT 'curated', scope TEXT NOT NULL DEFAULT 'global', scope_ref TEXT, importance INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'active', title TEXT, summary TEXT, tenant_id TEXT NOT NULL DEFAULT 'default', expires_at TEXT, workspace_id TEXT REFERENCES workspaces(id));

CREATE TABLE judgments (
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

CREATE TABLE reflections (
    id              TEXT PRIMARY KEY,
    owner_friend_id TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    turn_id         TEXT NOT NULL,
    score           REAL NOT NULL DEFAULT 0,
    summary         TEXT NOT NULL,
    lessons         TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE skills (
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

CREATE TABLE skill_runs (
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

CREATE TABLE invites (
    id              TEXT PRIMARY KEY,
    friend_id       TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    code            TEXT NOT NULL UNIQUE,
    expires_at      TEXT,
    used_at         TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE human_sessions (
    friend_id       TEXT PRIMARY KEY REFERENCES friends(id) ON DELETE CASCADE,
    channel         TEXT NOT NULL,
    endpoint        TEXT,
    auth_token_ref  TEXT,
    presence        TEXT NOT NULL DEFAULT 'offline',
    typing_until    TEXT,
    last_seen_at    TEXT,
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE assistant_global_settings (
    id          TEXT PRIMARY KEY,
    settings    TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE assistant_policy_templates (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    settings    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE assistant_queue_jobs (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    payload      TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    attempts     INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    run_at       TEXT NOT NULL,
    last_error   TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
, tenant_id TEXT NOT NULL DEFAULT 'default');

CREATE TABLE assistant_todos (
    id              TEXT PRIMARY KEY,
    owner_friend_id TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    detail          TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    priority        INTEGER NOT NULL DEFAULT 1,
    source_turn_id  TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
, repeat_rule TEXT, next_run_at TEXT);

CREATE TABLE workspaces (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id),
    owner_friend_id     TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    owner_user_id       TEXT REFERENCES users(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    path                TEXT NOT NULL,
    is_default          INTEGER NOT NULL DEFAULT 0,
    cli_session_mode    TEXT,
    cli_session_id      TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE user_workspace_prefs (
    user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    friend_id           TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    active_workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (user_id, friend_id)
);

CREATE TABLE cli_sessions (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id),
    workspace_id        TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    tool                TEXT NOT NULL,
    native_session_id   TEXT,
    label               TEXT,
    source_path         TEXT,
    is_active           INTEGER NOT NULL DEFAULT 0,
    last_used_at        TEXT,
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE users (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    username        TEXT,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'member',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(tenant_id, email),
    UNIQUE(tenant_id, username)
);

CREATE TABLE user_sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,
    expires_at      TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE group_workspaces (
    id TEXT PRIMARY KEY NOT NULL,
    group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'logical',
    git_url TEXT,
    default_branch TEXT,
    logical_key TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE group_member_bindings (
    id TEXT PRIMARY KEY NOT NULL,
    group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    group_workspace_id TEXT NOT NULL REFERENCES group_workspaces(id) ON DELETE CASCADE,
    friend_id TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    execution_mode TEXT,
    relay_id TEXT,
    local_path TEXT,
    UNIQUE(group_workspace_id, friend_id)
);

CREATE TABLE tenant_invites (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    code                TEXT NOT NULL UNIQUE,
    invited_email       TEXT,
    role                TEXT NOT NULL DEFAULT 'member',
    created_by_user_id  TEXT REFERENCES users(id) ON DELETE SET NULL,
    expires_at          TEXT NOT NULL,
    used_at             TEXT,
    used_by_user_id     TEXT REFERENCES users(id) ON DELETE SET NULL,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE agent_dna (
    tenant_id   TEXT PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    settings    TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    sender_name,
    content='messages',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE memories_fts USING fts5(
    content,
    kind UNINDEXED,
    content='memories',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE INDEX idx_friends_kind ON friends(backend_kind);

CREATE UNIQUE INDEX idx_conversations_dm_shared
    ON conversations(tenant_id, kind, target_id)
    WHERE kind = 'dm' AND scope_user_id IS NULL;

CREATE UNIQUE INDEX idx_conversations_dm_user
    ON conversations(tenant_id, kind, target_id, scope_user_id)
    WHERE kind = 'dm' AND scope_user_id IS NOT NULL;

CREATE UNIQUE INDEX idx_conversations_group
    ON conversations(tenant_id, kind, target_id)
    WHERE kind = 'group';

CREATE INDEX idx_conversations_target ON conversations(kind, target_id);

CREATE INDEX idx_messages_conv ON messages(conversation_id, created_at);

CREATE INDEX idx_messages_turn ON messages(turn_id);

CREATE INDEX idx_judgments_message ON judgments(message_id);

CREATE INDEX idx_memories_owner ON memories(owner_friend_id, kind);

CREATE INDEX idx_memories_weight ON memories(owner_friend_id, weight DESC);

CREATE INDEX idx_skills_owner ON skills(owner_friend_id);

CREATE INDEX idx_skill_runs_owner ON skill_runs(owner_friend_id, candidate_name);

CREATE INDEX idx_invites_friend ON invites(friend_id);

CREATE INDEX idx_assistant_todos_owner_status
ON assistant_todos(owner_friend_id, status, priority, updated_at);

CREATE INDEX idx_assistant_queue_jobs_due
ON assistant_queue_jobs(status, run_at);

CREATE INDEX idx_memories_recall
    ON memories(owner_friend_id, tier, status, scope, importance DESC);

CREATE INDEX idx_memories_tenant_owner
    ON memories(tenant_id, owner_friend_id);

CREATE INDEX idx_memories_expires
    ON memories(expires_at)
    WHERE expires_at IS NOT NULL;

CREATE INDEX idx_workspaces_friend
    ON workspaces(tenant_id, owner_friend_id);

CREATE INDEX idx_workspaces_user_scope
    ON workspaces(tenant_id, owner_friend_id, owner_user_id);

CREATE UNIQUE INDEX idx_workspaces_default_shared
    ON workspaces(owner_friend_id)
    WHERE is_default = 1 AND owner_user_id IS NULL;

CREATE UNIQUE INDEX idx_workspaces_default_user
    ON workspaces(tenant_id, owner_friend_id, owner_user_id)
    WHERE is_default = 1 AND owner_user_id IS NOT NULL;

CREATE INDEX idx_memories_workspace
    ON memories(workspace_id)
    WHERE workspace_id IS NOT NULL;

CREATE INDEX idx_messages_workspace
    ON messages(workspace_id)
    WHERE workspace_id IS NOT NULL;

CREATE INDEX idx_cli_sessions_workspace
    ON cli_sessions(tenant_id, workspace_id, tool);

CREATE UNIQUE INDEX idx_cli_sessions_workspace_tool_active
    ON cli_sessions(workspace_id, tool)
    WHERE is_active = 1;

CREATE UNIQUE INDEX idx_cli_sessions_source_path
    ON cli_sessions(source_path)
    WHERE source_path IS NOT NULL;

CREATE UNIQUE INDEX idx_tenants_slug ON tenants(slug);

CREATE INDEX idx_users_tenant ON users(tenant_id);

CREATE UNIQUE INDEX idx_users_tenant_username
    ON users(tenant_id, username);

CREATE INDEX idx_user_sessions_user ON user_sessions(user_id);

CREATE INDEX idx_user_sessions_expires ON user_sessions(expires_at);

CREATE INDEX idx_friends_tenant ON friends(tenant_id);

CREATE INDEX idx_groups_tenant ON groups(tenant_id);

CREATE INDEX idx_conversations_tenant ON conversations(tenant_id);

CREATE INDEX idx_group_workspaces_group ON group_workspaces(group_id);

CREATE UNIQUE INDEX idx_group_workspaces_logical
    ON group_workspaces(group_id, logical_key)
    WHERE logical_key IS NOT NULL;

CREATE INDEX idx_group_member_bindings_group ON group_member_bindings(group_id);

CREATE INDEX idx_group_member_bindings_friend ON group_member_bindings(friend_id);

CREATE INDEX idx_providers_tenant ON providers(tenant_id);

CREATE INDEX idx_provider_keys_tenant_provider
    ON provider_keys(tenant_id, provider_id);

CREATE INDEX idx_assistant_queue_jobs_tenant_due
    ON assistant_queue_jobs(tenant_id, status, run_at);

CREATE INDEX idx_tenant_invites_tenant ON tenant_invites(tenant_id);

CREATE INDEX idx_tenant_invites_expires ON tenant_invites(expires_at);

CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, sender_name) VALUES (new.rowid, new.content, new.sender_name);
END;

CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, sender_name) VALUES('delete', old.rowid, old.content, old.sender_name);
END;

CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, sender_name) VALUES('delete', old.rowid, old.content, old.sender_name);
    INSERT INTO messages_fts(rowid, content, sender_name) VALUES (new.rowid, new.content, new.sender_name);
END;

CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, kind) VALUES (new.rowid, new.content, new.kind);
END;

CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, kind) VALUES('delete', old.rowid, old.content, old.kind);
END;

CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, kind) VALUES('delete', old.rowid, old.content, old.kind);
    INSERT INTO memories_fts(rowid, content, kind) VALUES (new.rowid, new.content, new.kind);
END;

INSERT OR IGNORE INTO tenants (id, name) VALUES ('default', 'Default');

INSERT OR IGNORE INTO assistant_global_settings (id, settings, updated_at)
VALUES ('default', '{}', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
