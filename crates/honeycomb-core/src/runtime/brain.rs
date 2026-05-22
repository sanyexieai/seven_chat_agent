//! 命名约定（产品级）：
//! - **Agent 好友** — 统一走 `AgentRuntime`；含普通 Agent（`api` / `pty`）与 **助理**（`assistant`）
//! - **真人好友** — `HumanAgent`
//! - **Worker Bee CLI** — 独立 crate `worker-bee-cli`，二进制 `worker-bee`（工蜂）

pub use worker_bee_cli::{WORKER_BEE_CLI_BIN, WORKER_BEE_CLI_PRESET};

/// Agent 运行时（服务端编排层）对外名称。
pub const RUNTIME_NAME: &str = "蜂巢";
