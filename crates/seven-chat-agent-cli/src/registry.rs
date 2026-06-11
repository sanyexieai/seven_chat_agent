use seven_chat_agent_cli_protocol::{
    CliAuthProbe, CliDriver, CliError, CliLaunchConfig, Result,
    is_external_cli_preset, is_worker_bee_preset, PRESET_CLAUDE, PRESET_CODEX, PRESET_CURSOR,
    PRESET_WORKER_BEE,
};
use seven_chat_agent_cli_claude::ClaudeDriver;
use seven_chat_agent_cli_codex::CodexDriver;
use seven_chat_agent_cli_cursor::CursorDriver;
use seven_chat_agent_cli_worker_bee::WorkerBeeDriver;

static CODEX: CodexDriver = CodexDriver;
static CURSOR: CursorDriver = CursorDriver;
static CLAUDE: ClaudeDriver = ClaudeDriver;
static WORKER_BEE: WorkerBeeDriver = WorkerBeeDriver;

/// 按预设 ID 获取 CLI 驱动。
pub fn driver_for_preset(preset: &str) -> Option<&'static dyn CliDriver> {
    match preset {
        PRESET_CODEX => Some(&CODEX),
        PRESET_CURSOR => Some(&CURSOR),
        PRESET_CLAUDE => Some(&CLAUDE),
        PRESET_WORKER_BEE => Some(&WORKER_BEE),
        _ => None,
    }
}

/// 构建 exec argv；未知预设返回空 vec。
pub fn exec_argv(
    preset: &str,
    launch: &CliLaunchConfig,
    workspace: Option<&str>,
) -> Vec<String> {
    driver_for_preset(preset)
        .map(|d| d.exec_argv(launch, workspace))
        .unwrap_or_default()
}

pub fn resolve_executable(preset: &str, launch: &CliLaunchConfig) -> String {
    driver_for_preset(preset)
        .map(|d| d.resolve_executable(launch))
        .unwrap_or_else(|| launch.cmd.clone())
}

pub fn ensure_executable(preset: &str, launch: &CliLaunchConfig) -> Result<String> {
    let Some(driver) = driver_for_preset(preset) else {
        return Err(CliError::bad_request(format!("未知 CLI 预设: {preset}")));
    };
    driver.ensure_executable(launch)
}

pub fn api_key_env_var(preset: &str) -> Option<&'static str> {
    driver_for_preset(preset).and_then(|d| d.api_key_env_var())
}

pub fn uses_codex_jsonl_stream(preset: &str) -> bool {
    driver_for_preset(preset)
        .is_some_and(|d| d.uses_codex_jsonl_stream())
}

pub fn uses_cursor_stream_json(preset: &str) -> bool {
    preset == PRESET_CURSOR
}

pub fn parse_session_id(preset: &str, output: &[u8]) -> Option<String> {
    driver_for_preset(preset)
        .and_then(|d| d.parse_session_id(output))
}

pub fn resume_session_likely_invalid(preset: &str, output: &[u8]) -> bool {
    driver_for_preset(preset)
        .is_some_and(|d| d.resume_session_likely_invalid(output))
}

pub async fn prepare_resume_session(
    preset: &str,
    launch: &CliLaunchConfig,
    cmd: &str,
) -> Result<Option<String>> {
    let Some(driver) = driver_for_preset(preset) else {
        return Ok(None);
    };
    driver.prepare_resume_session(launch, cmd).await
}

pub async fn probe_auth(
    preset: &str,
    cmd: &str,
    api_key_configured: bool,
) -> CliAuthProbe {
    let Some(driver) = driver_for_preset(preset) else {
        return CliAuthProbe {
            preset: preset.into(),
            authenticated: api_key_configured,
            detail: if api_key_configured {
                "已配置 API Key（vault）".into()
            } else {
                "请配置 API Key 或在服务器上完成 CLI 登录".into()
            },
            api_key_configured,
        };
    };
    driver.probe_auth(cmd, api_key_configured).await
}

/// 从 `PtyBackendConfig` 风格字段解析有效预设（供 seven-chat-agent-core 调用）。
pub fn classify_pty_preset(
    preset: Option<&str>,
    cmd: &str,
    has_worker_bee_fields: bool,
) -> Option<String> {
    if is_external_cli_preset(preset) {
        return preset.map(str::to_string);
    }
    if is_worker_bee_preset(preset) || cmd == worker_bee_cli::WORKER_BEE_CLI_BIN {
        return Some(PRESET_WORKER_BEE.into());
    }
    if has_worker_bee_fields {
        return Some(PRESET_WORKER_BEE.into());
    }
    preset.filter(|p| !p.trim().is_empty() && *p != "custom")
        .map(str::to_string)
}
