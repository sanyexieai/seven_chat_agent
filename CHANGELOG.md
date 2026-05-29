# Changelog

## [2.0.0] — 2026-05-29

### 概述

**Seven Chat Agent v2** 使用 Rust 重写（`honeycomb-core` 内核），替代 [v1 FastAPI 版](https://github.com/sanyexieai/seven_chat_agent/releases/tag/v1.0.0)（`agent-backend` / `agent-ui`）。产品定位延续：多智能体、群聊、知识库式记忆与技能、MCP/LLM 配置，实现架构全面升级。

### 亮点

- 类微信多 Agent / 真人同屏聊天，群聊调度与 Judge
- 工蜂（Worker Bee）实例 + 外部 CLI（Codex / Claude / Cursor）
- Provider 矩阵（OpenAI 兼容 / Anthropic / Gemini / Ollama 等），Base URL 可配置
- CLI 远程转发（`honeycomb-cli-relay`）
- Web / Tauri 桌面 / TUI 三端
- 内置助理 Hex、群任务流、群代理人替身逻辑

### 说明

- 二进制与 crate 名仍保留 `honeycomb-*` 前缀（内部代号），与仓库名 `seven_chat_agent` 并存。
- 环境变量前缀仍为 `HONEYCOMB_*`。
- v1 代码可通过 Git 标签 `v1.0.0` 或分支 `legacy/v1-fastapi` 查阅（推送 v2 后请在 GitHub 上为旧 main 打 tag）。
