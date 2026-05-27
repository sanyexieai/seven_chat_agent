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

use crate::agent::{Agent, AgentEvent, AgentKind, ChatContext, Judgment, ProviderUsageInfo};
use crate::cli_workspace;
use crate::domain::{Friend, Message, PtyBackendConfig};
use crate::friend_cli::{codex_exec_args, pty_cli_session_is_resume};
use crate::judge::JudgeService;
use crate::provider::ProviderRegistry;
use crate::store::SqliteStore;
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
    pub fn from_config(cfg: &PtyBackendConfig) -> crate::Result<Self> {
        Self::from_config_for_friend(cfg, "")
    }

    pub fn from_config_for_friend(cfg: &PtyBackendConfig, friend_id: &str) -> crate::Result<Self> {
        let preset = crate::friend_cli::resolve_pty_preset(cfg)?;
        let mut adapter = match preset.as_str() {
            "codex-exec" => PtyAdapter::preset_codex_exec(),
            "worker-bee-cli" => PtyAdapter::preset_worker_bee_cli(),
            "claude" => PtyAdapter::preset_claude(),
            "cursor" => PtyAdapter::preset_cursor(),
            _ => PtyAdapter::generic(),
        };
        // 具名预设自带 cmd/args；仅 custom / 未知预设才允许 backend_config 覆盖。
        let cmd_overridable = preset == "custom" || adapter.label == "generic";
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
        Ok(adapter)
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
    store: Arc<SqliteStore>,
    judge: Arc<JudgeService>,
    adapter: PtyAdapter,
    last_raw: Arc<Mutex<Option<Vec<u8>>>>,
}

impl PtyAgent {
    pub fn new(
        friend: Friend,
        store: Arc<SqliteStore>,
        _providers: Arc<ProviderRegistry>,
        judge: Arc<JudgeService>,
    ) -> Result<Self> {
        let cfg: PtyBackendConfig = serde_json::from_value(friend.backend_config.clone())
            .map_err(|e| Error::Config(format!("invalid pty backend_config: {e}")))?;
        let mut adapter = PtyAdapter::from_config_for_friend(&cfg, &friend.id)?;
        apply_cli_session_adapter(&mut adapter, &cfg);
        Ok(Self {
            friend,
            store,
            judge,
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
        let friend_id = self.friend.id.clone();
        let store = self.store.clone();
        let fallback_adapter = self.adapter.clone();
        let raw_store = self.last_raw.clone();

        let s = stream! {
            let (mut cfg, mut adapter) = match load_pty_session_state(&store, &friend_id, &fallback_adapter).await {
                Ok(v) => v,
                Err(e) => {
                    yield AgentEvent::Error(e.to_string());
                    return;
                }
            };

            let resume = pty_cli_session_is_resume(&cfg) && adapter.label == "codex-exec";
            let composed_prompt = if resume {
                prompt.clone()
            } else {
                let history_excerpt = render_history(&ctx, &friend_id);
                if history_excerpt.is_empty() {
                    prompt.clone()
                } else {
                    format!("{history_excerpt}\n\n[最新消息]\n{prompt}")
                }
            };

            let raw_buf = Arc::new(Mutex::new(Vec::<u8>::new()));
            let mut retried_fresh = false;

            loop {
                let raw_for_save = raw_buf.clone();
                match run_oneshot(adapter.clone(), composed_prompt.clone(), raw_for_save).await {
                    Ok(stream_rx) => {
                        let mut rx = stream_rx;
                        while let Some(chunk) = rx.recv().await {
                            match chunk {
                                PtyStreamChunk::CliDelta(d) => yield AgentEvent::CliDelta(d),
                                PtyStreamChunk::Text(t) => yield AgentEvent::Token(t),
                            }
                        }
                        yield AgentEvent::Done(ProviderUsageInfo {
                            model: Some(adapter.label.clone()),
                            tokens_in: 0,
                            tokens_out: 0,
                        });
                    }
                    Err(e) => {
                        yield AgentEvent::Error(e.to_string());
                        break;
                    }
                }

                let buf = raw_buf.lock().await.clone();
                *raw_store.lock().await = Some(buf.clone());

                if resume
                    && cfg
                        .cli_thread_id
                        .as_ref()
                        .is_some_and(|s| !s.trim().is_empty())
                    && codex_resume_likely_invalid(&buf)
                    && !retried_fresh
                {
                    retried_fresh = true;
                    let _ = store.patch_friend_cli_thread_id(&friend_id, None).await;
                    cfg.cli_thread_id = None;
                    adapter.args = codex_exec_args(None);
                    apply_cli_session_adapter(&mut adapter, &cfg);
                    raw_buf.lock().await.clear();
                    continue;
                }

                if resume {
                    if let Some(tid) = worker_bee_cli::parse_codex_thread_id_from_jsonl(&buf) {
                        if cfg.cli_thread_id.as_deref() != Some(tid.as_str()) {
                            let _ = store
                                .patch_friend_cli_thread_id(&friend_id, Some(tid.clone()))
                                .await;
                            cfg.cli_thread_id = Some(tid);
                        }
                    }
                }
                break;
            }
        };

        Ok(Box::pin(s))
    }

    async fn judge(&self, ctx: ChatContext, msg: &Message) -> Result<Judgment> {
        let Some(settings) = ctx.group_settings.as_ref() else {
            return Ok(Judgment::default());
        };
        Ok(self
            .judge
            .evaluate_member(settings, &self.friend, None, &ctx.history, msg)
            .await)
    }
}

async fn load_pty_session_state(
    store: &SqliteStore,
    friend_id: &str,
    fallback_adapter: &PtyAdapter,
) -> Result<(PtyBackendConfig, PtyAdapter)> {
    let friend = store
        .get_friend(friend_id)
        .await?
        .ok_or_else(|| Error::not_found(format!("friend {friend_id}")))?;
    let cfg: PtyBackendConfig = serde_json::from_value(friend.backend_config.clone())
        .map_err(|e| Error::Config(format!("invalid pty backend_config: {e}")))?;
    let mut adapter =
        PtyAdapter::from_config_for_friend(&cfg, friend_id).unwrap_or_else(|_| fallback_adapter.clone());
    apply_cli_session_adapter(&mut adapter, &cfg);
    Ok((cfg, adapter))
}

fn apply_cli_session_adapter(adapter: &mut PtyAdapter, cfg: &PtyBackendConfig) {
    if adapter.label != "codex-exec" || !pty_cli_session_is_resume(cfg) {
        return;
    }
    let tid = cfg
        .cli_thread_id
        .as_deref()
        .filter(|s| !s.trim().is_empty());
    adapter.args = codex_exec_args(tid);
}

/// Codex `exec resume` 失败时（会话 id 失效等）回退为全新 `exec`。
fn codex_resume_likely_invalid(buf: &[u8]) -> bool {
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

#[derive(Debug, Clone)]
enum PtyStreamChunk {
    CliDelta(worker_bee_cli::CliBlockDelta),
    Text(String),
}

async fn run_oneshot(
    adapter: PtyAdapter,
    prompt: String,
    raw_buf: Arc<Mutex<Vec<u8>>>,
) -> Result<tokio::sync::mpsc::Receiver<PtyStreamChunk>> {
    use tokio::sync::mpsc;
    let (tx, rx) = mpsc::channel::<PtyStreamChunk>(64);

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
            return Err(Error::agent(format!(
                "CLI 工作目录不存在: {cwd}（请检查好友 cwd 或从项目根目录启动 honeycomb-server）"
            )));
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
        let mut codex_block_parser = worker_bee_cli::CodexExecJsonlBlockParser::default();

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
                                        for delta in codex_block_parser.push_line(line) {
                                            for part in worker_bee_cli::stream_split_cli_delta(
                                                delta,
                                                cli_stream_chunk_chars(),
                                            ) {
                                                let _ = tx
                                                    .send(PtyStreamChunk::CliDelta(part))
                                                    .await;
                                                tokio::task::yield_now().await;
                                            }
                                        }
                                    }
                                }
                            } else if !chunk.is_empty() {
                                let _ = tx.send(PtyStreamChunk::Text(chunk)).await;
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
            for delta in codex_block_parser.push_line(line_buf.trim()) {
                for part in worker_bee_cli::stream_split_cli_delta(delta, cli_stream_chunk_chars())
                {
                    let _ = tx.send(PtyStreamChunk::CliDelta(part)).await;
                    tokio::task::yield_now().await;
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
                            .send(PtyStreamChunk::Text(format!(
                                "\n（Codex CLI 报错：{}）",
                                trimmed.lines().next().unwrap_or(trimmed)
                            )))
                            .await;
                    } else {
                        tracing::debug!(stderr = %trimmed, "codex-exec stderr (suppressed from chat)");
                    }
                } else if !trimmed.is_empty() {
                    let _ = tx.send(PtyStreamChunk::Text(format!("\n[stderr] {s}"))).await;
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

fn cli_stream_chunk_chars() -> usize {
    std::env::var("HONEYCOMB_CLI_STREAM_CHUNK")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(32)
        .clamp(8, 256)
}

fn decode_chunk(bytes: &[u8], strip: bool) -> String {
    let cleaned = if strip {
        strip_ansi_escapes::strip(bytes)
    } else {
        bytes.to_vec()
    };
    String::from_utf8_lossy(&cleaned).to_string()
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
        || s.contains("No such file or directory")
        || s.contains("error:")
        || s.contains("Error:")
        || s.contains("failed")
}


