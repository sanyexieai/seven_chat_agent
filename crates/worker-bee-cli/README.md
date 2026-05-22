# worker-bee-cli

**Worker Bee**（工蜂）是 honeycomb 自研的 Agent CLI，接口形态参考 OpenAI `codex exec`，进程内提供记忆、MCP、Skill。

## 构建

```bash
cargo build -p worker-bee-cli --release
# 二进制: target/release/worker-bee
```

安装到 PATH 后，honeycomb CLI 好友 / 助理可选用 `preset=worker-bee-cli`。

## 用法

```bash
worker-bee exec "你好" --json --skip-git-repo-check
worker-bee exec -C /path/to/workspace "总结这个仓库"
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `WORKER_BEE_WORKSPACE` | 工作区根目录（默认当前目录） |
| `WORKER_BEE_DATA` | 记忆等数据目录（默认 `{workspace}/.worker-bee`） |
| `WORKER_BEE_SKILLS_DIR` | Skill 库目录（默认 `{workspace}/skills` 或 `data/skills`） |
