use crate::agent::pty::PtyAdapter;
use crate::domain::PtyBackendConfig;
use crate::friend_cli::ensure_worker_bee_executable;
use crate::runtime::WORKER_BEE_CLI_PRESET;
use crate::provider::types::{ChatMessage, ProviderUsage};
use crate::{Error, Result};

use super::ThinkResult;

/// CLI 好友的本机推理引擎（claude / codex-exec / 工蜂 CLI 等）。
#[derive(Debug, Clone)]
pub struct CliInferenceBackend {
    pub preset: String,
    pub cmd: Option<String>,
    pub cwd: Option<String>,
    pub friend_id: String,
}

impl CliInferenceBackend {
    pub async fn complete(&self, messages: &[ChatMessage]) -> Result<ThinkResult> {
        let prompt = messages_to_prompt(messages);
        let mut cfg = PtyBackendConfig {
            preset: Some(self.preset.clone()),
            cwd: self.cwd.clone(),
            ..Default::default()
        };
        if self.preset == "custom" {
            cfg.cmd = self.cmd.clone().unwrap_or_else(|| "claude".into());
            cfg.preset = None;
        }
        let mut adapter = PtyAdapter::from_config_for_friend(&cfg, &self.friend_id)?;
        if self.preset == WORKER_BEE_CLI_PRESET || adapter.label == "worker-bee-cli" {
            adapter.cmd = ensure_worker_bee_executable()?;
        }
        let text = run_cli_oneshot_collect(adapter, prompt).await?;
        let label = format!(
            "cli:{}",
            self.cmd.as_deref().unwrap_or(self.preset.as_str())
        );
        Ok(ThinkResult {
            text,
            label,
            usage: ProviderUsage::default(),
        })
    }
}

pub(crate) fn messages_to_prompt(messages: &[ChatMessage]) -> String {
    let mut out = String::new();
    for m in messages {
        out.push_str(&format!("[{}]\n{}\n\n", m.role, m.text()));
    }
    out
}

pub(crate) async fn run_cli_oneshot_collect(
    adapter: PtyAdapter,
    prompt: String,
) -> Result<String> {
    use std::process::Stdio;
    use tokio::io::AsyncReadExt;
    use tokio::process::Command;

    let mut cmd = Command::new(&adapter.cmd);
    let mut args = adapter.args.clone();
    args.push(prompt);
    cmd.args(&args);
    for (k, v) in &adapter.env {
        cmd.env(k, v);
    }
    if let Some(cwd) = &adapter.cwd {
        cmd.current_dir(cwd);
    }
    cmd.stdin(Stdio::null());
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());

    let mut child = cmd
        .spawn()
        .map_err(|e| Error::agent(format!("cli inference spawn {}: {e}", adapter.cmd)))?;

    let mut stdout = child.stdout.take().expect("stdout");
    let mut buf = Vec::new();
    let mut chunk = [0u8; 4096];
    loop {
        match stdout.read(&mut chunk).await {
            Ok(0) => break,
            Ok(n) => buf.extend_from_slice(&chunk[..n]),
            Err(_) => break,
        }
    }
    let _ = child.wait().await;

    if adapter.uses_codex_exec_jsonl() {
        let blocks = worker_bee_cli::parse_codex_exec_jsonl_to_blocks(&buf);
        if blocks.is_empty() {
            return Ok(String::from_utf8_lossy(&buf).to_string());
        }
        return Ok(worker_bee_cli::cli_blocks_to_plain(&blocks));
    }
    Ok(String::from_utf8_lossy(&buf).to_string())
}
