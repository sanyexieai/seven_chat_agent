use async_trait::async_trait;
use seven_chat_agent_cli_protocol::{
    CliAuthProbe, CliDriver, CliLaunchConfig, Result, CODEX_SANDBOX_DANGER, CODEX_SANDBOX_READ_ONLY,
    CODEX_SANDBOX_WORKSPACE_WRITE, PRESET_CODEX,
};
use worker_bee_cli::parse_codex_thread_id_from_jsonl;

pub struct CodexDriver;

impl CodexDriver {
    pub fn exec_args(session_id: Option<&str>, sandbox_mode: &str) -> Vec<String> {
        let mut args = vec!["exec".into()];
        let resuming = session_id.is_some_and(|s| !s.trim().is_empty());
        if let Some(tid) = session_id.filter(|s| !s.trim().is_empty()) {
            args.push("resume".into());
            args.push(tid.trim().to_string());
        }
        args.push("--skip-git-repo-check".into());
        append_codex_sandbox_flags(&mut args, sandbox_mode, resuming);
        if !resuming {
            args.push("--color".into());
            args.push("never".into());
        }
        args.push("--json".into());
        args
    }

    pub fn resume_session_likely_invalid(buf: &[u8]) -> bool {
        let lower = String::from_utf8_lossy(buf).to_lowercase();
        if lower.contains("turn.failed") {
            return true;
        }
        (lower.contains("session") || lower.contains("thread"))
            && (lower.contains("not found")
                || lower.contains("unknown")
                || lower.contains("invalid")
                || lower.contains("no such"))
    }
}

fn append_codex_sandbox_flags(args: &mut Vec<String>, sandbox_mode: &str, resuming: bool) {
    match sandbox_mode {
        CODEX_SANDBOX_WORKSPACE_WRITE if resuming => args.push("--full-auto".into()),
        CODEX_SANDBOX_WORKSPACE_WRITE => {
            args.push("--sandbox".into());
            args.push(CODEX_SANDBOX_WORKSPACE_WRITE.into());
        }
        CODEX_SANDBOX_DANGER if resuming => args.push("--dangerously-bypass-approvals-and-sandbox".into()),
        CODEX_SANDBOX_DANGER => {
            args.push("--sandbox".into());
            args.push(CODEX_SANDBOX_DANGER.into());
        }
        CODEX_SANDBOX_READ_ONLY if !resuming => {
            args.push("--sandbox".into());
            args.push(CODEX_SANDBOX_READ_ONLY.into());
        }
        _ => {}
    }
}

#[async_trait]
impl CliDriver for CodexDriver {
    fn preset_id(&self) -> &'static str { PRESET_CODEX }
    fn default_cmd(&self) -> &'static str { "codex" }
    fn resolve_executable(&self, launch: &CliLaunchConfig) -> String {
        if !launch.cmd.trim().is_empty() { launch.cmd.trim().to_string() } else { self.default_cmd().into() }
    }
    fn ensure_executable(&self, launch: &CliLaunchConfig) -> Result<String> { Ok(self.resolve_executable(launch)) }
    fn exec_argv(&self, launch: &CliLaunchConfig, _workspace: Option<&str>) -> Vec<String> {
        Self::exec_args(launch.session_id(), launch.sandbox_mode())
    }
    fn parse_session_id(&self, output: &[u8]) -> Option<String> { parse_codex_thread_id_from_jsonl(output) }
    fn resume_session_likely_invalid(&self, output: &[u8]) -> bool { Self::resume_session_likely_invalid(output) }
    fn api_key_env_var(&self) -> Option<&'static str> { Some("OPENAI_API_KEY") }
    fn uses_codex_jsonl_stream(&self) -> bool { true }
    async fn probe_auth(&self, cmd: &str, api_key_configured: bool) -> CliAuthProbe {
        let mut status = CliAuthProbe { preset: PRESET_CODEX.into(), authenticated: false, detail: String::new(), api_key_configured };
        let out = tokio::process::Command::new(cmd).args(["login", "status"]).output().await;
        match out {
            Ok(o) => {
                let text = format!("{}{}", String::from_utf8_lossy(&o.stdout), String::from_utf8_lossy(&o.stderr));
                status.authenticated = text.contains("Logged in") || text.contains("logged in");
                status.detail = text.trim().to_string();
                if !status.authenticated && api_key_configured {
                    status.authenticated = true;
                    status.detail = "已配置 OPENAI_API_KEY（vault）".into();
                }
            }
            Err(e) => status.detail = format!("无法执行 codex login status: {e}"),
        }
        status
    }
}
