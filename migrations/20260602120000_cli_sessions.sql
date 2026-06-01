-- 每工作区多 CLI 原生会话（Codex thread / Claude session / Cursor chat）
CREATE TABLE IF NOT EXISTS cli_sessions (
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

CREATE INDEX IF NOT EXISTS idx_cli_sessions_workspace
    ON cli_sessions(tenant_id, workspace_id, tool);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cli_sessions_workspace_tool_active
    ON cli_sessions(workspace_id, tool)
    WHERE is_active = 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cli_sessions_source_path
    ON cli_sessions(source_path)
    WHERE source_path IS NOT NULL;
