pub const CLI_SESSION_ONESHOT: &str = "oneshot";
pub const CLI_SESSION_RESUME: &str = "resume";

pub const CODEX_SANDBOX_READ_ONLY: &str = "read-only";
pub const CODEX_SANDBOX_WORKSPACE_WRITE: &str = "workspace-write";
pub const CODEX_SANDBOX_DANGER: &str = "danger-full-access";
pub const CODEX_SANDBOX_DEFAULT: &str = CODEX_SANDBOX_WORKSPACE_WRITE;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CliSessionMode {
    Oneshot,
    Resume,
}

impl CliSessionMode {
    pub fn from_config_str(s: Option<&str>) -> Self {
        if s == Some(CLI_SESSION_RESUME) {
            Self::Resume
        } else {
            Self::Oneshot
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct CliLaunchConfig {
    pub preset: String,
    pub cmd: String,
    pub cli_session_mode: Option<String>,
    pub cli_session_id: Option<String>,
    pub cli_sandbox_mode: Option<String>,
}

impl CliLaunchConfig {
    pub fn session_mode(&self) -> CliSessionMode {
        CliSessionMode::from_config_str(self.cli_session_mode.as_deref())
    }

    pub fn session_id(&self) -> Option<&str> {
        self.cli_session_id.as_deref().filter(|s| !s.trim().is_empty())
    }

    pub fn sandbox_mode(&self) -> &'static str {
        resolve_codex_sandbox_mode(self.cli_sandbox_mode.as_deref())
    }
}

pub fn resolve_codex_sandbox_mode(mode: Option<&str>) -> &'static str {
    match mode {
        Some(CODEX_SANDBOX_READ_ONLY) => CODEX_SANDBOX_READ_ONLY,
        Some(CODEX_SANDBOX_DANGER) => CODEX_SANDBOX_DANGER,
        Some(CODEX_SANDBOX_WORKSPACE_WRITE) | None => CODEX_SANDBOX_WORKSPACE_WRITE,
        Some(other) if other.trim().is_empty() => CODEX_SANDBOX_DEFAULT,
        Some(_) => CODEX_SANDBOX_WORKSPACE_WRITE,
    }
}
