use std::path::Path;
use std::process::Stdio;
use std::sync::Arc;
use std::time::Duration;

use async_stream::stream;
use async_trait::async_trait;
use futures::stream::BoxStream;
use serde::{Deserialize, Serialize};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::process::Command;
use tokio::sync::Mutex;
use tracing::warn;

use crate::agent::api::ApiAgent;
use crate::agent::{Agent, AgentEvent, AgentKind, ChatContext, Judgment, ProviderUsageInfo};
use crate::cli_workspace;
use crate::domain::{Friend, Message, PtyBackendConfig};
use crate::provider::ProviderRegistry;
use crate::{Error, Result};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PtyMode {
    Oneshot,
    Repl,
}

impl Default for PtyMode {
    fn default() -> Self {
        Self::Oneshot
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum InputMode {
    Stdin,
    ArgAppend,
    ArgTemplate,
}

impl Default for InputMode {
    fn default() -> Self {
        Self::ArgAppend
    }
}

#[derive(Debug, Clone)]
pub struct PtyAdapter {
    pub label: String,
    pub mode: PtyMode,
    pub cmd: String,
    pub args: Vec<String>,
    pub env: Vec<(String, String)>,
    pub cwd: Option<String>,
    pub input_mode: InputMode,
    pub arg_template_placeholder: String,
    pub strip_ansi: bool,
    pub timeout_seconds: u64,
}

impl PtyAdapter {
    pub fn from_config(cfg: &PtyBackendConfig) -> Self {
        Self::from_config_for_friend(cfg, "")
    }

    pub fn from_config_for_friend(cfg: &PtyBackendConfig, friend_id: &str) -> Self {
        let preset = cfg
            .preset
            .as_deref()
            .filter(|s| !s.is_empty())
            .unwrap_or("claude");
        let mut adapter = match preset {
            "codex-exec" => PtyAdapter::preset_codex_exec(),
            "worker-bee-cli" => PtyAdapter::preset_worker_bee_cli(),
            "claude" => PtyAdapter::preset_claude(),
            "cursor" => PtyAdapter::preset_cursor(),
            _ => PtyAdapter::generic(),
        };
        // 具名预设自带 cmd/args；仅 custom / 未知预设才允许 backend_config 覆盖。
        let cmd_overridable = matches!(preset, "custom") || adapter.label == "generic";
        if cmd_overridable && !cfg.cmd.is_empty() {
            adapter.cmd = cfg.cmd.clone();
        }
        if cmd_overridable && !cfg.args.is_empty() {
            adapter.args = cfg.args.clone();
        }
        if !cfg.env.is_empty() {
            adapter.env = cfg.env.clone();
        }
        if let Ok(cwd) = resolve_pty_cwd(cfg, friend_id) {
            adapter.cwd = Some(cwd.clone());
            if adapter.label == "codex-exec" || adapter.label == "worker-bee-cli" {
                ensure_codex_exec_cd(&mut adapter.args, &cwd);
            }
        }
        if let Some(s) = cfg.idle_seconds {
            adapter.timeout_seconds = s.max(5);
        }
        adapter
    }

    /// OpenAI `codex exec` CLI（`preset=codex-exec`）。
    pub fn preset_codex_exec() -> Self {
        // exec 在非 git / 未 trust 的目录会抛 skip-git-repo-check；--json 便于解析 agent_message。
        Self {
            label: "codex-exec".into(),
            mode: PtyMode::Oneshot,
            cmd: "codex".into(),
            args: vec![
                "exec".into(),
                "--skip-git-repo-check".into(),
                "--color".into(),
                "never".into(),
                "--json".into(),
            ],
            env: vec![],
            cwd: None,
            input_mode: InputMode::ArgAppend,
            arg_template_placeholder: "{input}".into(),
            strip_ansi: true,
            timeout_seconds: 180,
        }
    }

    /// 自研 **Worker Bee CLI**（crate `worker-bee-cli`；工蜂；参考 codex exec）。
    pub fn preset_worker_bee_cli() -> Self {
        Self {
            label: "worker-bee-cli".into(),
            mode: PtyMode::Oneshot,
            cmd: crate::friend_cli::resolve_worker_bee_executable(),
            args: vec![
                "exec".into(),
                "--skip-git-repo-check".into(),
                "--color".into(),
                "never".into(),
                "--json".into(),
            ],
            env: vec![],
            cwd: None,
            input_mode: InputMode::ArgAppend,
            arg_template_placeholder: "{input}".into(),
            strip_ansi: true,
            timeout_seconds: 180,
        }
    }

    pub(crate) fn uses_codex_exec_jsonl(&self) -> bool {
        (self.label == "codex-exec" || self.label == "worker-bee-cli")
            && self.args.iter().any(|a| a == "--json")
    }

    pub fn preset_claude() -> Self {
        Self {
            label: "claude".into(),
            mode: PtyMode::Oneshot,
            cmd: "claude".into(),
            args: vec!["-p".into()],
            env: vec![],
            cwd: None,
            input_mode: InputMode::ArgAppend,
            arg_template_placeholder: "{input}".into(),
            strip_ansi: true,
            timeout_seconds: 180,
        }
    }

    pub fn preset_cursor() -> Self {
        Self {
            label: "cursor".into(),
            mode: PtyMode::Oneshot,
            cmd: "cursor-agent".into(),
            args: vec!["-p".into()],
            env: vec![],
            cwd: None,
            input_mode: InputMode::ArgAppend,
            arg_template_placeholder: "{input}".into(),
            strip_ansi: true,
            timeout_seconds: 180,
        }
    }

    pub fn generic() -> Self {
        Self {
            label: "generic".into(),
            mode: PtyMode::Oneshot,
            cmd: "cat".into(),
            args: vec![],
            env: vec![],
            cwd: None,
            input_mode: InputMode::Stdin,
            arg_template_placeholder: "{input}".into(),
            strip_ansi: true,
            timeout_seconds: 60,
        }
    }
}

pub struct PtyAgent {
    friend: Friend,
    providers: Arc<ProviderRegistry>,
    adapter: PtyAdapter,
    last_raw: Arc<Mutex<Option<Vec<u8>>>>,
}

impl PtyAgent {
    pub fn new(friend: Friend, providers: Arc<ProviderRegistry>) -> Result<Self> {
        let cfg: PtyBackendConfig = serde_json::from_value(friend.backend_config.clone())
            .map_err(|e| Error::Config(format!("invalid pty backend_config: {e}")))?;
        let adapter = PtyAdapter::from_config_for_friend(&cfg, &friend.id);
        Ok(Self {
            friend,
            providers,
            adapter,
            last_raw: Arc::new(Mutex::new(None)),
        })
    }

    pub async fn last_raw_output(&self) -> Option<Vec<u8>> {
        self.last_raw.lock().await.clone()
    }
}

#[async_trait]
impl Agent for PtyAgent {
    fn kind(&self) -> AgentKind {
        AgentKind::Pty
    }

    async fn send(
        &self,
        ctx: ChatContext,
        prompt: String,
    ) -> Result<BoxStream<'static, AgentEvent>> {
        let adapter = self.adapter.clone();
        let history_excerpt = render_history(&ctx, &self.friend.id);
        let composed_prompt = if history_excerpt.is_empty() {
            prompt.clone()
        } else {
            format!("{history_excerpt}\n\n[最新消息]\n{prompt}")
        };
        let raw_buf = Arc::new(Mutex::new(Vec::<u8>::new()));
        let raw_for_save = raw_buf.clone();
        let raw_store = self.last_raw.clone();

        let s = stream! {
            match run_oneshot(adapter.clone(), composed_prompt, raw_for_save).await {
                Ok(stream_rx) => {
                    let mut rx = stream_rx;
                    while let Some(text) = rx.recv().await {
                        yield AgentEvent::Token(text);
                    }
                    yield AgentEvent::Done(ProviderUsageInfo {
                        model: Some(adapter.label.clone()),
                        tokens_in: 0,
                        tokens_out: 0,
                    });
                    let buf = raw_buf.lock().await.clone();
                    *raw_store.lock().await = Some(buf);
                }
                Err(e) => {
                    yield AgentEvent::Error(e.to_string());
                }
            }
        };

        Ok(Box::pin(s))
    }

    async fn judge(&self, ctx: ChatContext, msg: &Message) -> Result<Judgment> {
        if let Some(provider_id) = self.friend.judge_provider_ref.clone() {
            let stub_cfg = serde_json::json!({
                "provider_id": provider_id,
                "model": std::env::var("HONEYCOMB_JUDGE_MODEL")
                    .unwrap_or_else(|_| "gpt-4o-mini".into()),
            });
            let mut surrogate = self.friend.clone();
            surrogate.backend_kind = crate::domain::BackendKind::Api;
            surrogate.backend_config = stub_cfg;
            if let Ok(api) = ApiAgent::new(surrogate, self.providers.clone()) {
                return api.judge(ctx, msg).await;
            }
        }
        Ok(Judgment {
            should_reply: false,
            confidence: 0.0,
            reason: Some("PtyAgent 需要配置 judge_provider_ref 才能参与群聊判断".into()),
            suggested_delay_ms: 0,
        })
    }
}

fn render_history(ctx: &ChatContext, self_id: &str) -> String {
    let mut out = String::new();
    let history = &ctx.history;
    let take = history.len().saturating_sub(1);
    for m in history.iter().take(take) {
        let tag = match m.sender_kind {
            crate::domain::SenderKind::User => "user".to_string(),
            crate::domain::SenderKind::Friend if m.sender_id == self_id => "self".into(),
            crate::domain::SenderKind::Friend => format!("peer:{}", m.sender_name),
            crate::domain::SenderKind::System => "system".into(),
        };
        out.push_str(&format!("[{}] {}\n", tag, m.content));
    }
    out.trim_end().to_string()
}

async fn run_oneshot(
    adapter: PtyAdapter,
    prompt: String,
    raw_buf: Arc<Mutex<Vec<u8>>>,
) -> Result<tokio::sync::mpsc::Receiver<String>> {
    use tokio::sync::mpsc;
    let (tx, rx) = mpsc::channel::<String>(64);

    let mut cmd = Command::new(&adapter.cmd);
    let mut args = adapter.args.clone();
    match adapter.input_mode {
        InputMode::Stdin => {}
        InputMode::ArgAppend => {
            args.push(prompt.clone());
        }
        InputMode::ArgTemplate => {
            for a in args.iter_mut() {
                *a = a.replace(&adapter.arg_template_placeholder, &prompt);
            }
        }
    }
    cmd.args(&args);
    for (k, v) in &adapter.env {
        cmd.env(k, v);
    }
    if let Some(cwd) = &adapter.cwd {
        let p = Path::new(cwd);
        if p.is_dir() {
            cmd.current_dir(p);
        } else {
            warn!(cwd = %cwd, "pty cwd does not exist, using server cwd");
        }
    }
    cmd.stdin(if adapter.input_mode == InputMode::Stdin {
        Stdio::piped()
    } else {
        Stdio::null()
    });
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());

    let mut child = cmd
        .spawn()
        .map_err(|e| Error::agent(format!("spawn {} failed: {e}", adapter.cmd)))?;

    if adapter.input_mode == InputMode::Stdin {
        if let Some(mut stdin) = child.stdin.take() {
            stdin
                .write_all(prompt.as_bytes())
                .await
                .map_err(Error::Io)?;
            stdin.shutdown().await.ok();
        }
    }

    let mut stdout = child.stdout.take().expect("piped");
    let mut stderr = child.stderr.take().expect("piped");

    let timeout = Duration::from_secs(adapter.timeout_seconds);
    let strip_ansi = adapter.strip_ansi;
    let raw_buf_inner = raw_buf.clone();
    let codex_exec_jsonl = adapter.uses_codex_exec_jsonl();

    tokio::spawn(async move {
        let mut buf = [0u8; 4096];
        let mut deadline = tokio::time::Instant::now() + timeout;
        let mut accumulated: Vec<u8> = Vec::new();
        let mut killed = false;
        let mut line_buf = String::new();
        let mut codex_exec_parser = CodexExecJsonlParser::default();

        loop {
            tokio::select! {
                read = stdout.read(&mut buf) => {
                    match read {
                        Ok(0) => break,
                        Ok(n) => {
                            accumulated.extend_from_slice(&buf[..n]);
                            raw_buf_inner.lock().await.extend_from_slice(&buf[..n]);
                            let chunk = decode_chunk(&buf[..n], strip_ansi);
                            if codex_exec_jsonl {
                                line_buf.push_str(&chunk);
                                while let Some(pos) = line_buf.find('\n') {
                                    let line: String = line_buf.drain(..=pos).collect();
                                    let line = line.trim();
                                    if !line.is_empty() {
                                        if let Some(delta) = codex_exec_parser.push_line(line) {
                                            if !delta.is_empty() {
                                                let _ = tx.send(delta).await;
                                            }
                                        }
                                    }
                                }
                            } else if !chunk.is_empty() {
                                let _ = tx.send(chunk).await;
                            }
                            deadline = tokio::time::Instant::now() + timeout;
                        }
                        Err(_) => break,
                    }
                }
                _ = tokio::time::sleep_until(deadline) => {
                    warn!("pty oneshot timeout, killing process");
                    let _ = child.kill().await;
                    killed = true;
                    break;
                }
            }
        }

        if codex_exec_jsonl && !line_buf.trim().is_empty() {
            if let Some(delta) = codex_exec_parser.push_line(line_buf.trim()) {
                if !delta.is_empty() {
                    let _ = tx.send(delta).await;
                }
            }
        }

        let mut errbuf = Vec::new();
        let _ = stderr.read_to_end(&mut errbuf).await;
        if !errbuf.is_empty() {
            let s = decode_chunk(&errbuf, strip_ansi);
            let trimmed = s.trim();
            if !trimmed.is_empty() {
                raw_buf_inner.lock().await.extend_from_slice(b"\n[stderr] ");
                raw_buf_inner.lock().await.extend_from_slice(&errbuf);
                if codex_exec_jsonl {
                    // JSON 模式下 stderr 多为 banner / 非致命提示，不打进聊天气泡。
                    if is_codex_exec_fatal_stderr(trimmed) {
                        let _ = tx
                            .send(format!(
                                "\n（Codex CLI 报错：{}）",
                                trimmed.lines().next().unwrap_or(trimmed)
                            ))
                            .await;
                    } else {
                        tracing::debug!(stderr = %trimmed, "codex-exec stderr (suppressed from chat)");
                    }
                } else if !trimmed.is_empty() {
                    let _ = tx.send(format!("\n[stderr] {s}")).await;
                }
            }
        }

        if !killed {
            let _ = child.wait().await;
        }
        let _ = accumulated;
    });

    Ok(rx)
}

fn decode_chunk(bytes: &[u8], strip: bool) -> String {
    let cleaned = if strip {
        strip_ansi_escapes::strip(bytes)
    } else {
        bytes.to_vec()
    };
    String::from_utf8_lossy(&cleaned).to_string()
}

#[derive(Default)]
struct CodexExecJsonlParser {
    emitted: String,
}

impl CodexExecJsonlParser {
    fn push_line(&mut self, line: &str) -> Option<String> {
        let v: serde_json::Value = serde_json::from_str(line).ok()?;
        if v.get("type")?.as_str()? != "item.completed" {
            return None;
        }
        let item = v.get("item")?;
        if item.get("type")?.as_str()? != "agent_message" {
            return None;
        }
        let text = item.get("text")?.as_str()?.to_string();
        if text.is_empty() {
            return None;
        }
        if text.starts_with(&self.emitted) {
            let delta = text[self.emitted.len()..].to_string();
            if delta.is_empty() {
                return None;
            }
            self.emitted = text;
            return Some(delta);
        }
        self.emitted = text.clone();
        Some(text)
    }
}

/// 工作目录优先级：好友 `cwd` > `HONEYCOMB_CLI_CWD` > 自动 `{HONEYCOMB_DATA}/cli-workspaces/{friend_id}`（建目录 + 可选 git init）。
fn resolve_pty_cwd(cfg: &PtyBackendConfig, friend_id: &str) -> Result<String> {
    if let Some(ref p) = cfg.cwd {
        let t = p.trim();
        if !t.is_empty() {
            return cli_workspace::ensure_at(t);
        }
    }
    if let Ok(global) = std::env::var("HONEYCOMB_CLI_CWD") {
        let t = global.trim();
        if !t.is_empty() {
            return cli_workspace::ensure_at(t);
        }
    }
    if friend_id.is_empty() {
        return Err(Error::Config(
            "pty friend id required to resolve default cli workspace".into(),
        ));
    }
    cli_workspace::ensure_for_friend(friend_id)
}

/// codex exec 除进程 `current_dir` 外还支持 `-C` 指定 agent 工作根目录。
fn ensure_codex_exec_cd(args: &mut Vec<String>, cwd: &str) {
    let mut i = 0;
    while i < args.len() {
        if args[i] == "-C" || args[i] == "--cd" {
            if i + 1 < args.len() {
                args[i + 1] = cwd.to_string();
            }
            return;
        }
        i += 1;
    }
    let insert_at = args.iter().position(|a| a == "exec").map(|p| p + 1).unwrap_or(0);
    args.insert(insert_at, cwd.to_string());
    args.insert(insert_at, "-C".into());
}

fn is_codex_exec_fatal_stderr(s: &str) -> bool {
    s.contains("Not inside a trusted directory")
        || s.contains("error:")
        || s.contains("Error:")
        || s.contains("failed")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codex_exec_jsonl_extracts_agent_message() {
        let line = r#"{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"你好"}}"#;
        let mut p = CodexExecJsonlParser::default();
        assert_eq!(p.push_line(line).as_deref(), Some("你好"));
        assert_eq!(p.push_line(line), None);
    }
}

