use async_trait::async_trait;
use honeycomb_cli_protocol::{CliAuthProbe, CliDriver, CliError, CliLaunchConfig, CliSessionMode, Result, PRESET_CURSOR};

pub const CURSOR_AGENT_ALIASES: &[&str] = &["agent", "cursor-agent"];

pub struct CursorDriver;

fn path_if_executable(p: &std::path::Path) -> Option<String> {
    p.is_file().then(|| p.to_string_lossy().into_owned())
}

fn cli_command_works(cmd: &str) -> bool {
    std::process::Command::new(cmd)
        .arg("--version")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn find_cursor_agent_in_share(versions_dir: &std::path::Path) -> Option<String> {
    let entries = std::fs::read_dir(versions_dir).ok()?;
    let mut stable = Vec::new();
    let mut tmp = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let name = path.file_name()?.to_string_lossy().into_owned();
        let bin = path.join("cursor-agent");
        if !bin.is_file() {
            continue;
        }
        if name.starts_with(".tmp-") {
            tmp.push(bin);
        } else {
            stable.push((name, bin));
        }
    }
    if let Some((_, bin)) = stable.into_iter().max_by(|a, b| a.0.cmp(&b.0)) {
        return Some(bin.to_string_lossy().into_owned());
    }
    tmp.into_iter().next().map(|p| p.to_string_lossy().into_owned())
}

impl CursorDriver {
    pub fn agent_args(workspace: Option<&str>, session_id: Option<&str>) -> Vec<String> {
        let mut args = vec!["-p".into(), "--trust".into(), "--output-format".into(), "text".into()];
        if let Some(id) = session_id.filter(|s| !s.trim().is_empty()) {
            args.push("--resume".into());
            args.push(id.trim().to_string());
        }
        if let Some(w) = workspace.filter(|s| !s.trim().is_empty()) {
            args.push("--workspace".into());
            args.push(w.trim().to_string());
        }
        args
    }

    pub fn resolve_executable(launch: &CliLaunchConfig) -> String {
        if let Ok(p) = std::env::var("HONEYCOMB_CURSOR_AGENT_BIN") {
            let t = p.trim();
            if !t.is_empty() {
                return t.to_string();
            }
        }
        if !launch.cmd.trim().is_empty() && launch.cmd != "agent" {
            return launch.cmd.trim().to_string();
        }
        for name in CURSOR_AGENT_ALIASES {
            if cli_command_works(name) {
                return (*name).into();
            }
        }
        if let Ok(home) = std::env::var("HOME") {
            let home = std::path::PathBuf::from(home);
            for rel in [".local/bin/agent", ".local/bin/cursor-agent"] {
                if let Some(path) = path_if_executable(&home.join(rel)) {
                    return path;
                }
            }
            if let Some(p) = find_cursor_agent_in_share(&home.join(".local/share/cursor-agent/versions")) {
                return p;
            }
        }
        "cursor-agent".into()
    }

    pub fn ensure_executable(launch: &CliLaunchConfig) -> Result<String> {
        let path = Self::resolve_executable(launch);
        if std::path::Path::new(&path).is_file() || cli_command_works(&path) {
            return Ok(path);
        }
        Err(CliError::agent("找不到 Cursor Agent CLI（尝试过 agent / cursor-agent）。请安装 Cursor Agent，或设置 HONEYCOMB_CURSOR_AGENT_BIN"))
    }
}

#[async_trait]
impl CliDriver for CursorDriver {
    fn preset_id(&self) -> &'static str { PRESET_CURSOR }
    fn default_cmd(&self) -> &'static str { "agent" }
    fn resolve_executable(&self, launch: &CliLaunchConfig) -> String { Self::resolve_executable(launch) }
    fn ensure_executable(&self, launch: &CliLaunchConfig) -> Result<String> { Self::ensure_executable(launch) }
    fn exec_argv(&self, launch: &CliLaunchConfig, workspace: Option<&str>) -> Vec<String> {
        Self::agent_args(workspace, launch.session_id())
    }
    fn parse_session_id(&self, _output: &[u8]) -> Option<String> { None }
    fn api_key_env_var(&self) -> Option<&'static str> { Some("CURSOR_API_KEY") }
    fn uses_codex_jsonl_stream(&self) -> bool { false }
    async fn prepare_resume_session(&self, launch: &CliLaunchConfig, cmd: &str) -> Result<Option<String>> {
        if launch.session_mode() != CliSessionMode::Resume || launch.session_id().is_some() {
            return Ok(None);
        }
        let out = tokio::process::Command::new(cmd)
            .arg("create-chat")
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .output()
            .await
            .map_err(|e| CliError::agent(format!("agent create-chat: {e}")))?;
        let id = String::from_utf8_lossy(&out.stdout).trim().to_string();
        if id.is_empty() {
            let err = String::from_utf8_lossy(&out.stderr);
            return Err(CliError::agent(format!("agent create-chat 未返回 chat id: {}", err.trim())));
        }
        Ok(Some(id))
    }
    async fn probe_auth(&self, cmd: &str, api_key_configured: bool) -> CliAuthProbe {
        let mut status = CliAuthProbe { preset: PRESET_CURSOR.into(), authenticated: false, detail: String::new(), api_key_configured };
        let out = tokio::process::Command::new(cmd).arg("status").output().await;
        match out {
            Ok(o) => {
                let text = String::from_utf8_lossy(&o.stdout);
                let err = String::from_utf8_lossy(&o.stderr);
                let combined = format!("{text}{err}");
                status.authenticated = combined.contains("Logged in") || combined.contains("logged in");
                status.detail = combined.trim().to_string();
                if !status.authenticated && api_key_configured {
                    status.authenticated = true;
                    status.detail = "已配置 CURSOR_API_KEY（vault）".into();
                }
            }
            Err(e) => status.detail = format!("无法执行 {cmd} status: {e}"),
        }
        status
    }
}
