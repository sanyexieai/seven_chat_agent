# 工作区与多租户设计

## 已实现（Phase A）

### 数据模型

- **`workspaces`**：绑定 `tenant_id` + `owner_friend_id`，字段含 `path`、`is_default`、`cli_session_mode`、`cli_session_id`
- **`friends.active_workspace_id`**：当前选用工作区
- **`memories.workspace_id`** / **`messages.workspace_id`**：写入时关联（DM 自动取对端好友 active workspace）

### 行为

1. 启动时 `migrate_all_friend_workspaces()`：为每个非 human 好友创建「默认」工作区，路径来自 legacy `backend_config.cwd` 或 `data/cli-workspaces/<好友ID>`
2. Pty 执行前 `load_pty_session_state` 合并 active workspace 的 path 与 CLI 会话 ID
3. `patch_friend_cli_session_id` 同步写入 active workspace 与 backend_config（兼容旧逻辑）
4. 记忆召回：`scope=workspace` + `workspace_id` 列过滤（global/user 仍跨工作区）

### API

| 方法 | 路径 |
|------|------|
| GET | `/friends/:id/workspaces` |
| POST | `/friends/:id/workspaces` |
| PATCH | `/friends/:id/workspaces/:ws_id` |
| DELETE | `/friends/:id/workspaces/:ws_id` |
| POST | `/friends/:id/workspaces/:ws_id/activate` |

Web 通过 ws-api：`listFriendWorkspaces`、`createFriendWorkspace`、`activateFriendWorkspace`、`deleteFriendWorkspace`。

### UI

- 好友编辑 → Pty 配置区「工作区（多项目）」
- 私聊顶栏：多工作区时下拉切换

## 多租户现状

- **记忆 / 全局策略**：`SEVEN_CHAT_AGENT_TENANT_ID` 隔离
- **工作区表**：含 `tenant_id`，与记忆租户一致
- **好友/会话/消息**：仍未全表 `tenant_id`（单实例部署可接受）

## 已实现（Phase B）

### `cli_sessions` 表

- 每工作区、每工具（`codex` / `claude` / `cursor`）可有多条会话；同工具仅一条 `is_active`
- Pty 续聊优先读 active `cli_sessions`，并同步 legacy `workspaces.cli_session_id` + `backend_config`

### Codex 导入

- `POST /friends/:id/workspaces/:ws_id/import-codex`：扫描 `CODEX_HOME` 或 `~/.codex/sessions` 下 `rollout-*.jsonl`
- 按 JSONL 内 `<cwd>` 与工作区 `path` 匹配；写入 `cli_sessions`，可选写入 raw 记忆（`[CLI导入/codex]`）

### API 补充

| 方法 | 路径 |
|------|------|
| GET | `.../workspaces/:ws_id/cli-sessions` |
| POST | `.../workspaces/:ws_id/cli-sessions/:session_id/activate` |
| POST | `.../workspaces/:ws_id/import-codex` |

## 已实现（Phase C）

### Claude 导入

- 扫描 `CLAUDE_CONFIG_DIR` 或 `~/.claude/projects/<编码路径>/*.jsonl`
- 从 JSONL 读取 `cwd`、`sessionId`、首条用户消息
- `POST .../workspaces/:ws_id/import-claude`

### Cursor 导入

- 扫描 `~/.cursor/projects/*/agent-transcripts/**/*.jsonl`
- `cwd` 缺失时用项目目录 slug（路径 `/` → `-`）与工作区路径模糊匹配
- `POST .../workspaces/:ws_id/import-cursor`

### 环境变量

| 变量 | 用途 |
|------|------|
| `CODEX_HOME` | Codex 状态目录（默认 `~/.codex`） |
| `CLAUDE_CONFIG_DIR` | Claude 配置根（默认 `~/.claude`） |
| `CURSOR_HOME` | Cursor 数据根（默认 `~/.cursor`） |

## 后续

- Cursor `state.vscdb` / `~/.cursor/chats` SQLite 深度导入
- 系统 messages 与 CLI transcript 对账面板
- 租户贯穿 friends/conversations 或分库
