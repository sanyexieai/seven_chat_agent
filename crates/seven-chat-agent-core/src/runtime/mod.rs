//! honeycomb **Agent 运行时**（`AgentRuntime`）：助理与 CLI 好友共用。
//! - **助理**：推理走 Provider 矩阵（各家 API）
//! - **CLI 好友**：推理走本机 CLI（codex / claude / Worker Bee 工蜂 CLI 等）
//! - 运行时提供记忆、技能、工具循环；工蜂 CLI 则在进程内自带 memory/mcp/skill

mod agent;
mod backends;
mod brain;
mod config;
mod engine;
mod memory;
pub(crate) mod provider_env;
mod tools;

pub use provider_env::{
    detect_provider_id_from_env, env_api_key_var, env_has_provider_key,
    resolve_worker_bee_provider,
};

pub use brain::{RUNTIME_NAME, WORKER_BEE_CLI_BIN, WORKER_BEE_CLI_PRESET};

pub use agent::UnifiedAgent;
pub use config::{
    CliInferenceConfig, InferenceBackend, ProviderInferenceConfig, RuntimeConfigOverlay,
    RuntimeProfile,
};
pub use engine::AgentRuntime;
