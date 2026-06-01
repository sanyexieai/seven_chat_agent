-- 好友多工作区：目录 + CLI 续聊会话（Phase A）
CREATE TABLE IF NOT EXISTS workspaces (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id),
    owner_friend_id     TEXT NOT NULL REFERENCES friends(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    path                TEXT NOT NULL,
    is_default          INTEGER NOT NULL DEFAULT 0,
    cli_session_mode    TEXT,
    cli_session_id      TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_workspaces_friend
    ON workspaces(tenant_id, owner_friend_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_one_default
    ON workspaces(owner_friend_id)
    WHERE is_default = 1;

ALTER TABLE friends ADD COLUMN active_workspace_id TEXT REFERENCES workspaces(id);

ALTER TABLE memories ADD COLUMN workspace_id TEXT REFERENCES workspaces(id);

ALTER TABLE messages ADD COLUMN workspace_id TEXT;

CREATE INDEX IF NOT EXISTS idx_memories_workspace
    ON memories(workspace_id)
    WHERE workspace_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_messages_workspace
    ON messages(workspace_id)
    WHERE workspace_id IS NOT NULL;
