# CLI 远程转发架构

## 分层

```
Web（发消息 / 配置好友）
    ↓  WebSocket /ws-api
服务端（Honeycomb Server）
    ↓  配对后 WebSocket /cli-relay
转发程序（honeycomb-cli-relay，跑在远程电脑）
    ↓  本机 spawn
CLI（codex / claude / cursor / worker-bee）
```

- **local（默认）**：服务端本机 `Command::spawn`，与改造前一致。
- **relay**：好友 `backend_config` 设置 `execution_mode: "relay"` 与 `relay_id`，由已配对的转发节点在本机执行。

## 配对流程

1. Web 调用 `createCliRelayPairingToken`，获得 15 分钟内有效的一次性 `pair_*` 令牌。
2. 在远程电脑运行：

```bash
cargo run -p honeycomb-cli-relay -- \
  --url ws://<server-host>:8080/cli-relay \
  --pairing-token pair_xxx \
  --name my-laptop
```

3. 服务端返回 `relay_*` 节点 id；Web 调用 `listCliRelays` 查看在线节点。
4. 编辑 CLI 好友：在 `backend_config` 中设置：

```json
{
  "execution_mode": "relay",
  "relay_id": "relay_xxxxxxxx",
  "preset": "codex-exec"
}
```

## 协议（`honeycomb-cli-relay-protocol`）

| 方向 | 类型 | 说明 |
|------|------|------|
| 转发→服 | `register` | 携带 `pairing_token` |
| 服→转发 | `registered` | 返回 `relay_id` |
| 服→转发 | `run_job` | `job_id`, `preset`, `prompt`, `cwd`, 会话字段 |
| 转发→服 | `job_output` | 流式 `text_delta`，`done=true` 结束 |

## 后续可增强

- 转发端 Codex JSONL 块解析与 `CliDelta` 事件对齐
- 好友编辑 UI：选择在线转发节点、一键生成配对码
- 多转发节点负载与亲和（按好友绑定）
- 转发端 API Key / OAuth 环境变量注入（与 vault 同步）
