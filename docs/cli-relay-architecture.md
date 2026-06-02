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
cargo run -p seven-chat-agent-cli-relay -- \
  --url ws://<server-host>:18737/cli-relay \
  --pairing-token pair_xxx \
  --name my-laptop
```

3. 转发端 `register` 携带 `workspace_root`；服务端返回 `relay_*` 节点 id。
4. Web 调用 `listCliRelays` 查看在线节点及远程工作区根目录。
5. 编辑 CLI 好友：设置 `execution_mode: "relay"` 与 `relay_id`。

## 协议（`seven-chat-agent-cli-relay-protocol`）

| 方向 | 类型 | 说明 |
|------|------|------|
| 转发→服 | `register` | `pairing_token`、`workspace_root` |
| 转发→服 | `workspace_report` | 工作区根目录变更 |
| 服→转发 | `registered` | 返回 `relay_id` |
| 服→转发 | `run_job` | `friend_id`、`group_id`、可选 `cwd` 覆盖、会话字段 |
| 转发→服 | `job_output` | 流式 `text_delta`，`done=true` 结束 |

## 后续可增强

- 转发端 Codex JSONL 块解析与 `CliDelta` 事件对齐
- 多转发节点负载与亲和（按好友绑定）
- 转发端 API Key / OAuth 环境变量注入（与 vault 同步）
