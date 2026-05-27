use async_trait::async_trait;

use crate::config::CliLaunchConfig;
use crate::error::Result;

#[derive(Debug, Clone, serde::Serialize)]
pub struct CliAuthProbe {
    pub preset: String,
    pub authenticated: bool,
    pub detail: String,
    pub api_key_configured: bool,
}

#[async_trait]
pub trait CliDriver: Send + Sync {
    fn preset_id(&self) -> &'static str;
    fn default_cmd(&self) -> &'static str;
    fn resolve_executable(&self, launch: &CliLaunchConfig) -> String;
    fn ensure_executable(&self, launch: &CliLaunchConfig) -> Result<String>;
    fn exec_argv(&self, launch: &CliLaunchConfig, workspace: Option<&str>) -> Vec<String>;
    fn parse_session_id(&self, output: &[u8]) -> Option<String>;

    fn resume_session_likely_invalid(&self, output: &[u8]) -> bool {
        let _ = output;
        false
    }

    fn api_key_env_var(&self) -> Option<&'static str>;
    fn uses_codex_jsonl_stream(&self) -> bool;

    async fn prepare_resume_session(
        &self,
        _launch: &CliLaunchConfig,
        _cmd: &str,
    ) -> Result<Option<String>> {
        Ok(None)
    }

    async fn probe_auth(&self, cmd: &str, api_key_configured: bool) -> CliAuthProbe;
}
