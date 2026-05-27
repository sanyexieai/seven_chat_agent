use async_trait::async_trait;
use honeycomb_cli_protocol::{CliAuthProbe, CliDriver, CliLaunchConfig, Result, PRESET_CLAUDE};

pub struct ClaudeDriver;

impl ClaudeDriver {
    pub fn print_args(session_id: Option<&str>) -> Vec<String> {
        let mut args = vec!["-p".into(), "--output-format".into(), "json".into()];
        if let Some(id) = session_id.filter(|s| !s.trim().is_empty()) {
            args.push("--resume".into());
            args.push(id.trim().to_string());
        }
        args
    }

    pub fn parse_session_id_from_output(buf: &[u8]) -> Option<String> {
        for line in String::from_utf8_lossy(buf).lines() {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            let Ok(v) = serde_json::from_str::<serde_json::Value>(line) else {
                continue;
            };
            if let Some(id) = v.get("session_id").and_then(|s| s.as_str()) {
                if !id.is_empty() {
                    return Some(id.to_string());
                }
            }
        }
        None
    }
}

#[async_trait]
impl CliDriver for ClaudeDriver {
    fn preset_id(&self) -> &'static str { PRESET_CLAUDE }
    fn default_cmd(&self) -> &'static str { "claude" }
    fn resolve_executable(&self, launch: &CliLaunchConfig) -> String {
        if !launch.cmd.trim().is_empty() { launch.cmd.trim().to_string() } else { self.default_cmd().into() }
    }
    fn ensure_executable(&self, launch: &CliLaunchConfig) -> Result<String> { Ok(self.resolve_executable(launch)) }
    fn exec_argv(&self, launch: &CliLaunchConfig, _workspace: Option<&str>) -> Vec<String> { Self::print_args(launch.session_id()) }
    fn parse_session_id(&self, output: &[u8]) -> Option<String> { Self::parse_session_id_from_output(output) }
    fn api_key_env_var(&self) -> Option<&'static str> { Some("ANTHROPIC_API_KEY") }
    fn uses_codex_jsonl_stream(&self) -> bool { false }
    async fn probe_auth(&self, cmd: &str, api_key_configured: bool) -> CliAuthProbe {
        let mut status = CliAuthProbe { preset: PRESET_CLAUDE.into(), authenticated: false, detail: String::new(), api_key_configured };
        let out = tokio::process::Command::new(cmd).args(["auth", "status"]).output().await;
        match out {
            Ok(o) => {
                let text = format!("{}{}", String::from_utf8_lossy(&o.stdout), String::from_utf8_lossy(&o.stderr));
                status.authenticated = text.contains("logged in") || text.contains("Logged in") || text.contains("authenticated");
                status.detail = text.trim().to_string();
                if !status.authenticated && api_key_configured {
                    status.authenticated = true;
                    status.detail = "已配置 ANTHROPIC_API_KEY（vault）".into();
                }
            }
            Err(_) => {
                status.detail = if api_key_configured {
                    status.authenticated = true;
                    "已配置 ANTHROPIC_API_KEY（vault）".into()
                } else {
                    "请配置 API Key 或发起 OAuth 登录".into()
                };
            }
        }
        status
    }
}
