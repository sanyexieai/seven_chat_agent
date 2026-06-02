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

详见 [多租户与用户体系.md](./多租户与用户体系.md)。

- **记忆 / 全局策略 / 工作区 / cli_sessions**：`tenant_id` 隔离
- **用户登录注册**：T1 已实现（可选 `AUTH_REQUIRED`）
- **friends / groups / conversations**：已加 `tenant_id` 列；全链路过滤进行中

## 已实现（Phase D · 按登录用户隔离工作区）

### 数据模型

- **`workspaces.owner_user_id`**：非空表示该工作区仅所属用户可见；`NULL` 为租户内共享（未登录 / 旧数据 / `AUTH_REQUIRED=0`）
- **`user_workspace_prefs`**：`(user_id, friend_id) → active_workspace_id`，每用户独立「当前工作区」

### 目录布局

登录用户默认路径：

`{CLI_WORKSPACE_ROOT}/tenants/{tenant_id}/users/{user_id}/{friend_id}/`

同租户内用户 A / 用户 B 对同一 Agent 好友各自拥有独立目录与 CLI 会话，互不可见。

### API / 运行时

- 带 `auth_token` 的请求：`SqliteStore.for_user(session.user_id)`，列表/创建/激活/PTY cwd 均按用户过滤
- 发消息时 `ACTIVE_USER` 传入 dispatcher，Agent 执行使用该用户的工作区
- 未登录：仍用 `owner_user_id IS NULL` 的共享工作区 + `friends.active_workspace_id`

### 已实现（Phase E · 私聊按用户拆分）

- **`conversations.scope_user_id`**：登录用户的 DM 唯一键为 `(tenant_id, dm, friend_id, scope_user_id)`；未登录 / 真人邀请为 `NULL`（共享线程）
- `get_or_create_dm` / `list_conversations` / 发消息调度均按 `scope_user_id` 过滤
- 调度器根据会话上的 `scope_user_id` 恢复 `ACTIVE_USER`，Agent 回复使用对端用户的工作区

## 群工作区与远程 CLI

群内 **relay** 成员不能共用服务端 `cli_workspace` 路径；runtime 已改为 relay 时回退好友工作区。逻辑项目 + Git 协调见多租户文档 §3。

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
