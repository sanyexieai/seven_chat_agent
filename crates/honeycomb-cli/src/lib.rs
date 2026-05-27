//! 蜂巢 CLI 驱动注册层：
//! - `honeycomb-cli-protocol`：抽象接口与共享类型
//! - `honeycomb-cli-codex` / `honeycomb-cli-claude` / `honeycomb-cli-cursor` / `honeycomb-cli-worker-bee`：具体实现
pub mod registry;
pub mod resolve;

pub use honeycomb_cli_protocol::{
    CliAuthProbe, CliDriver, CliError, CliLaunchConfig, CliSessionMode, Result,
    CLI_SESSION_ONESHOT, CLI_SESSION_RESUME, CODEX_SANDBOX_DANGER, CODEX_SANDBOX_DEFAULT,
    CODEX_SANDBOX_READ_ONLY, CODEX_SANDBOX_WORKSPACE_WRITE, resolve_codex_sandbox_mode,
    is_external_cli_preset, is_worker_bee_preset, uses_codex_exec_protocol, EXTERNAL_CLI_PRESETS,
    PRESET_CLAUDE, PRESET_CODEX, PRESET_CURSOR, PRESET_WORKER_BEE
};
pub use honeycomb_cli_claude::ClaudeDriver;
pub use honeycomb_cli_codex::CodexDriver;
pub use honeycomb_cli_cursor::{CursorDriver, CURSOR_AGENT_ALIASES};
pub use honeycomb_cli_worker_bee::WorkerBeeDriver;
pub use registry::{
    api_key_env_var, classify_pty_preset, driver_for_preset, ensure_executable, exec_argv,
    parse_session_id, prepare_resume_session, probe_auth, resolve_executable,
    resume_session_likely_invalid, uses_codex_jsonl_stream,
};

// 向后兼容：与 `worker-bee-cli` 常量一致
pub use worker_bee_cli::{WORKER_BEE_CLI_BIN, WORKER_BEE_CLI_PRESET};
