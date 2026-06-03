# CLI 远程转发架构

## 分层

```
Web（发消息 / 配置好友）
    ↓  WebSocket /ws-api
服务端（SevenChatAgent Server）
    ↓  配对后 WebSocket /cli-relay
转发程序（seven-chat-agent-cli-relay，跑在远程电脑）
    ↓  本机 spawn
CLI（codex / claude / cursor / worker-bee）
```

- **local（默认）**：服务端本机 `Command::spawn`，工作区在服务端 `data/cli-workspaces/…`。
- **relay**：好友 `backend_config` 设置 `execution_mode: "relay"` 与 `relay_id`；**工作区由转发程序在远程自行决定并上报**，服务端不下发 cwd。

## 工作区约定（relay）

转发端在注册时上报 `workspace_root`（绝对路径）。优先级：

1. 启动参数 `--workspace-root`
2. 环境变量 `SEVEN_CHAT_AGENT_RELAY_WORKSPACE_ROOT`
3. 默认 `~/.local/share/seven-chat-agent/cli-workspaces`

单次任务 cwd 解析（均在转发端本机）：

| 场景 | 路径 |
|------|------|
| 私聊 | `{workspace_root}/friends/{friend_id}` |
| 群聊 | `{workspace_root}/groups/{group_id}` |
| 群成员 binding.local_path | 使用该覆盖路径 |

服务端通过 `listCliRelays` 展示 `workspace_root`；Web 可推算 `{workspace_root}/friends/{friend_id}` 供用户查看。

## 配对流程

1. Web 调用 `createCliRelayPairingToken`，获得 15 分钟内有效的一次性 `pair_*` 令牌。
2. 在远程电脑运行：

```bash
# 仅 HTTP：ws://<host>:18737/cli-relay
# 已启用 HTTPS（示例站）：wss://3ye.co:18743/cli-relay
cargo run -p seven-chat-agent-cli-relay -- \
  --url wss://<server-host>:18743/cli-relay \
  --pairing-token pair_xxx \
  --name my-laptop
```

3. 转发端 `register` 携带 `workspace_root` 与本机 `cli_auth` 探测结果；服务端返回 `relay_*` 节点 id。
4. 转发端每 60s 及每次任务结束后发送 `auth_report` 更新登录状态。
5. Web 调用 `listCliRelays` 查看在线节点、工作区与远程 CLI 鉴权。
6. 编辑 CLI 好友：设置 `execution_mode: "relay"` 与 `relay_id`；**鉴权以转发端为准**，勿在服务器点 OAuth。

配对 WebSocket 地址优先级：Web **设置 → CLI 转发**（全局 `cli_relay_ws_url` + `cli_relay_ws_scheme`：`auto`/`ws`/`wss`）→ `SEVEN_CHAT_AGENT_RELAY_WS_URL` → `SEVEN_CHAT_AGENT_PUBLIC_ORIGIN` → HTTPS 绑定 + `PUBLIC_HOST`。`auto` 在已启用 TLS 时将 `ws://` 升级为 `wss://`。

## 协议（`seven-chat-agent-cli-relay-protocol`）

| 方向 | 类型 | 说明 |
|------|------|------|
| 转发→服 | `register` | `pairing_token`、`workspace_root` |
| 转发→服 | `workspace_report` | 工作区根目录变更 |
| 服→转发 | `registered` | 返回 `relay_id` |
| 服→转发 | `run_job` | `friend_id`、`group_id`、可选 `cwd` 覆盖、会话字段 |
| 转发→服 | `job_output` | 流式 `text_delta` 或 `cli_delta`（Codex JSONL 解析后），`done=true` 结束 |

## 后续可增强

- ~~转发端 Codex JSONL 块解析与 `CliDelta` 事件对齐~~（已实现）
- 转发任务流式推送至 Web（当前任务结束后一次性渲染结构化块）
- 多转发节点负载与亲和（按好友绑定）
- 转发端 API Key / OAuth 环境变量注入（与 vault 同步）
