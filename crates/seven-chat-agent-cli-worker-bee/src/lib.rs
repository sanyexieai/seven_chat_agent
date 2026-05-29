use async_trait::async_trait;
use seven_chat_agent_cli_protocol::{CliAuthProbe, CliDriver, CliError, CliLaunchConfig, Result, PRESET_WORKER_BEE};
use seven_chat_agent_cli_codex::CodexDriver;
use worker_bee_cli::{parse_codex_thread_id_from_jsonl, WORKER_BEE_CLI_BIN};

fn path_if_executable(p: &std::path::Path) -> Option<String> {
    p.is_file().then(|| p.to_string_lossy().into_owned())
}

fn cli_command_help_works(cmd: &str) -> bool {
    std::process::Command::new(cmd)
        .arg("--help")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

pub struct WorkerBeeDriver;

impl WorkerBeeDriver {
    pub fn resolve_executable() -> String {
        if let Ok(p) = std::env::var("SEVEN_CHAT_AGENT_WORKER_BEE_BIN") {
            let t = p.trim();
            if !t.is_empty() {
                return t.to_string();
            }
        }
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                if let Some(p) = path_if_executable(&dir.join(WORKER_BEE_CLI_BIN)) {
                    return p;
                }
                for rel in ["debug/worker-bee", "release/worker-bee"] {
                    if let Some(p) = path_if_executable(&dir.join(rel)) {
                        return p;
                    }
                }
            }
        }
        if cli_command_help_works(WORKER_BEE_CLI_BIN) {
            return WORKER_BEE_CLI_BIN.into();
        }
        WORKER_BEE_CLI_BIN.into()
    }

    pub fn ensure_executable() -> Result<String> {
        let path = Self::resolve_executable();
        if std::path::Path::new(&path).is_file() || cli_command_help_works(&path) {
            return Ok(path);
        }
        Err(CliError::agent(format!(
            "找不到 worker-bee 可执行文件（解析为「{path}」）。请构建 worker-bee-cli，或设置 SEVEN_CHAT_AGENT_WORKER_BEE_BIN"
        )))
    }
}

#[async_trait]
impl CliDriver for WorkerBeeDriver {
    fn preset_id(&self) -> &'static str { PRESET_WORKER_BEE }
    fn default_cmd(&self) -> &'static str { WORKER_BEE_CLI_BIN }
    fn resolve_executable(&self, launch: &CliLaunchConfig) -> String {
        if !launch.cmd.trim().is_empty() { launch.cmd.trim().to_string() } else { Self::resolve_executable() }
    }
    fn ensure_executable(&self, launch: &CliLaunchConfig) -> Result<String> {
        if !launch.cmd.trim().is_empty() {
            let p = launch.cmd.trim();
            if std::path::Path::new(p).is_file() || cli_command_help_works(p) {
                return Ok(p.to_string());
            }
        }
        Self::ensure_executable()
    }
    fn exec_argv(&self, launch: &CliLaunchConfig, _workspace: Option<&str>) -> Vec<String> {
        CodexDriver::exec_args(launch.session_id(), launch.sandbox_mode())
    }
    fn parse_session_id(&self, output: &[u8]) -> Option<String> { parse_codex_thread_id_from_jsonl(output) }
    fn resume_session_likely_invalid(&self, output: &[u8]) -> bool { CodexDriver::resume_session_likely_invalid(output) }
    fn api_key_env_var(&self) -> Option<&'static str> { None }
    fn uses_codex_jsonl_stream(&self) -> bool { true }
    async fn probe_auth(&self, cmd: &str, api_key_configured: bool) -> CliAuthProbe {
        let works = cli_command_help_works(cmd);
        CliAuthProbe {
            preset: PRESET_WORKER_BEE.into(),
            authenticated: works || api_key_configured,
            detail: if works { format!("worker-bee 可执行: {cmd}") } else { "请构建 worker-bee-cli 或设置 SEVEN_CHAT_AGENT_WORKER_BEE_BIN".into() },
            api_key_configured,
        }
    }
}
