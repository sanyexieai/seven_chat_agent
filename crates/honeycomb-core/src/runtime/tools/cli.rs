use async_trait::async_trait;
use serde_json::Value;
use std::sync::Arc;
use tokio::sync::Mutex;

use super::{Tool, ToolContext};
use crate::agent::pty::PtyAdapter;
use crate::domain::PtyBackendConfig;
use crate::Result;

pub struct CliTool;

#[async_trait]
impl Tool for CliTool {
    fn name(&self) -> &'static str {
        "cli"
    }

    fn description(&self) -> &'static str {
        "调用本机 cli（claude code / cursor-agent 等，oneshot）。arguments: {\"prompt\":\"...\"}"
    }

    async fn execute(&self, ctx: &ToolContext, args: &Value) -> Result<String> {
        let prompt = args
            .get("prompt")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim();
        if prompt.is_empty() {
            return Ok("cli: 缺少 prompt".into());
        }
        let preset = ctx.cli_preset.as_deref().unwrap_or("claude");
        let mut cfg = PtyBackendConfig {
            preset: Some(preset.into()),
            cwd: Some(ctx.workspace_cwd.clone()),
            ..Default::default()
        };
        if preset == "custom" {
            cfg.cmd = ctx.cli_cmd.clone().unwrap_or_else(|| "claude".into());
            cfg.preset = None;
        }
        let adapter = PtyAdapter::from_config_for_friend(&cfg, &ctx.friend_id);
        let raw = Arc::new(Mutex::new(String::new()));
        let acc = raw.clone();
        let mut rx = run_pty_oneshot(adapter, prompt.to_string()).await?;
        while let Some(chunk) = rx.recv().await {
            acc.lock().await.push_str(&chunk);
        }
        let out = raw.lock().await.clone();
        if out.trim().is_empty() {
            return Ok("cli: 无输出".into());
        }
        Ok(out)
    }
}

async fn run_pty_oneshot(
    adapter: PtyAdapter,
    prompt: String,
) -> Result<tokio::sync::mpsc::Receiver<String>> {
    use std::process::Stdio;
    use tokio::io::AsyncReadExt;
    use tokio::process::Command;

    let (tx, rx) = tokio::sync::mpsc::channel(64);
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
        .map_err(|e| crate::Error::agent(format!("cli spawn {}: {e}", adapter.cmd)))?;
    let mut stdout = child.stdout.take().expect("stdout");
    tokio::spawn(async move {
        let mut buf = [0u8; 4096];
        loop {
            match stdout.read(&mut buf).await {
                Ok(0) => break,
                Ok(n) => {
                    let s = String::from_utf8_lossy(&buf[..n]).to_string();
                    if !s.is_empty() {
                        let _ = tx.send(s).await;
                    }
                }
                Err(_) => break,
            }
        }
        let _ = child.wait().await;
    });
    Ok(rx)
}
