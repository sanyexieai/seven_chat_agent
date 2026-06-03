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
use crate::cli_relay::{RelayHub, RelayJobSpec};
use crate::domain::{Friend, Message, PtyBackendConfig};
use crate::friend_cli::{
    apply_cli_auth_env, cli_auth_env_pairs, ensure_cursor_agent_executable,
    ensure_cursor_chat_session,
    effective_pty_preset, external_cli_argv, is_external_cli_preset, launch_from_pty,
    parse_session_id, pty_cli_session_is_resume, pty_execution_is_relay, pty_relay_id,
    resolve_cli_session_id, resolve_cli_workspace,
    resume_session_likely_invalid, uses_codex_jsonl_stream,
};
use crate::store::SecretVault;
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
        if adapter.label == "cursor" && !pty_execution_is_relay(cfg) {
            adapter.cmd = ensure_cursor_agent_executable()?;
        }
        if let Ok(cwd) = resolve_pty_cwd(cfg, friend_id) {
            adapter.cwd = Some(cwd.clone());
            if adapter.label == "codex-exec" || adapter.label == "worker-bee-cli" {
                ensure_codex_exec_cd(&mut adapter.args, &cwd);
            }
        }
        if is_external_cli_preset(cfg)
            || cfg.preset.as_deref() == Some(seven_chat_agent_cli::PRESET_WORKER_BEE)
        {
            apply_cli_session_adapter(&mut adapter, cfg);
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
        uses_codex_jsonl_stream(&self.label) && self.args.iter().any(|a| a == "--json")
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
            cmd: "agent".into(),
            args: crate::friend_cli::cursor_agent_args(None, None),
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
    cli_relay: Arc<RelayHub>,
    adapter: PtyAdapter,
    last_raw: Arc<Mutex<Option<Vec<u8>>>>,
}

impl PtyAgent {
    pub fn new(
        friend: Friend,
        store: Arc<SqliteStore>,
        _providers: Arc<ProviderRegistry>,
        judge: Arc<JudgeService>,
        cli_relay: Arc<RelayHub>,
    ) -> Result<Self> {
        let cfg: PtyBackendConfig = serde_json::from_value(friend.backend_config.clone())
            .map_err(|e| Error::Config(format!("invalid pty backend_config: {e}")))?;
        let mut adapter = PtyAdapter::from_config_for_friend(&cfg, &friend.id)?;
        apply_cli_session_adapter(&mut adapter, &cfg);
        Ok(Self {
            friend,
            store,
            judge,
            cli_relay,
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
        let cli_relay = self.cli_relay.clone();

        let s = stream! {
            let (mut cfg, mut adapter) = match load_pty_session_state(&store, &friend_id, &fallback_adapter).await {
                Ok(v) => v,
                Err(e) => {
                    yield AgentEvent::Error(e.to_string());
                    return;
                }
            };

            let member_local_path = if let Some(gid) = ctx.group_id.as_deref() {
                store
                    .resolve_member_group_local_path(gid, &friend_id)
                    .await
                    .ok()
                    .flatten()
            } else {
                None
            };

            let is_relay = pty_execution_is_relay(&cfg);

            if is_relay {
                if let Some(relay_id) = pty_relay_id(&cfg) {
                    if let Some(ws) = cli_relay.workspace_path_for_friend(relay_id, &friend_id) {
                        adapter.cwd = Some(ws);
                    }
                }
            } else {
                match resolve_cli_workspace(
                    &cfg,
                    &friend_id,
                    ctx.group_id.as_deref(),
                    ctx.group_cli_workspace(),
                    member_local_path.as_deref(),
                ) {
                    Ok(ws) => {
                        adapter.cwd = Some(ws.clone());
                        cfg.cwd = Some(ws);
                    }
                    Err(e) => {
                        yield AgentEvent::Error(e.to_string());
                        return;
                    }
                }
            }

            let resume =
                pty_cli_session_is_resume(&cfg) && external_cli_label(&adapter.label).is_some();

            if resume && !is_relay {
                if adapter.label == "cursor" {
                    if let Err(e) =
                        ensure_cursor_chat_session(&adapter.cmd, &mut cfg, &store, &friend_id).await
                    {
                        yield AgentEvent::Error(e.to_string());
                        return;
                    }
                    apply_cli_session_adapter(&mut adapter, &cfg);
                }
            }

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

            if is_relay {
                let relay_id = match pty_relay_id(&cfg) {
                    Some(id) => id.to_string(),
                    None => {
                        yield AgentEvent::Error("已选择远程转发但未配置 relay_id".into());
                        return;
                    }
                };
                if !cli_relay.is_online(&relay_id) {
                    yield AgentEvent::Error(format!("转发节点 {relay_id} 未在线，请先在远程电脑启动 seven-chat-agent-cli-relay"));
                    return;
                }
                let preset = effective_pty_preset(&cfg);
                let mut env = cfg.env.clone();
                env.extend(cli_auth_env_pairs(&cfg, &store.vault));
                let cwd_override = member_local_path.or_else(|| {
                    cfg.cwd
                        .as_ref()
                        .filter(|p| !crate::friend_cli::looks_like_server_cli_workspace(p))
                        .cloned()
                });
                let spec = RelayJobSpec {
                    preset,
                    prompt: composed_prompt.clone(),
                    friend_id: friend_id.clone(),
                    group_id: ctx.group_id.clone(),
                    cwd_override,
                    cli_session_mode: cfg.cli_session_mode.clone(),
                    cli_session_id: cfg.cli_session_id.clone(),
                    env,
                };
                let timeout = Duration::from_secs(adapter.timeout_seconds);
                match cli_relay.run_job(&relay_id, spec, timeout).await {
                    Ok(result) => {
                        raw_buf.lock().await.extend_from_slice(result.text.as_bytes());
                        for delta in result.cli_deltas {
                            yield AgentEvent::CliDelta(delta);
                        }
                        if !result.text.is_empty() {
                            yield AgentEvent::Token(result.text);
                        }
                        yield AgentEvent::Done(ProviderUsageInfo {
                            model: Some(adapter.label.clone()),
                            tokens_in: 0,
                            tokens_out: 0,
                        });
                    }
                    Err(e) => yield AgentEvent::Error(e),
                }
                return;
            }

            loop {
                let raw_for_save = raw_buf.clone();
                match run_oneshot(
                    adapter.clone(),
                    composed_prompt.clone(),
                    raw_for_save,
                    &cfg,
                    store.vault.clone(),
                )
                .await
                {
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
                    && resolve_cli_session_id(&cfg).is_some()
                    && resume_session_likely_invalid(&adapter.label, &buf)
                    && !retried_fresh
                {
                    retried_fresh = true;
                    let _ = store.patch_friend_cli_session_id(&friend_id, None).await;
                    cfg.cli_session_id = None;
                    apply_cli_session_adapter(&mut adapter, &cfg);
                    raw_buf.lock().await.clear();
                    continue;
                }

                if resume {
                    let new_id = parse_session_id(&adapter.label, &buf);
                    if let Some(id) = new_id {
                        if resolve_cli_session_id(&cfg) != Some(id.as_str()) {
                            let _ = store
                                .patch_friend_cli_session_id(&friend_id, Some(id.clone()))
                                .await;
                            cfg.cli_session_id = Some(id);
                            apply_cli_session_adapter(&mut adapter, &cfg);
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
    let _ = store.ensure_friend_workspaces(friend_id).await;
    let friend = store
        .get_friend(friend_id)
        .await?
        .ok_or_else(|| Error::not_found(format!("friend {friend_id}")))?;
    let mut cfg: PtyBackendConfig = serde_json::from_value(friend.backend_config.clone())
        .map_err(|e| Error::Config(format!("invalid pty backend_config: {e}")))?;
    if let Ok(Some(ws)) = store.get_active_workspace(friend_id).await {
        let tool = crate::cli_tool::tool_for_preset(cfg.preset.as_deref());
        let sess = if let Some(tool) = tool {
            store
                .get_active_cli_session(&ws.id, tool)
                .await
                .ok()
                .flatten()
        } else {
            None
        };
        crate::store::cli_session::apply_workspace_and_cli_session(
            &mut cfg,
            &ws,
            sess.as_ref(),
        );
    }
    let mut adapter =
        PtyAdapter::from_config_for_friend(&cfg, friend_id).unwrap_or_else(|_| fallback_adapter.clone());
    if is_external_cli_preset(&cfg)
        || cfg.preset.as_deref() == Some(seven_chat_agent_cli::PRESET_WORKER_BEE)
    {
        apply_cli_session_adapter(&mut adapter, &cfg);
    }
    Ok((cfg, adapter))
}

fn external_cli_label(label: &str) -> Option<&'static str> {
    match label {
        "codex-exec" => Some("codex-exec"),
        "cursor" => Some("cursor"),
        "claude" => Some("claude"),
        _ => None,
    }
}

fn apply_cli_session_adapter(adapter: &mut PtyAdapter, cfg: &PtyBackendConfig) {
    let preset = match external_cli_label(&adapter.label) {
        Some(p) => p,
        None => return,
    };
    let mut launch = launch_from_pty(cfg);
    if !pty_cli_session_is_resume(cfg) {
        launch.cli_session_id = None;
    }
    adapter.args = external_cli_argv(preset, &launch, adapter.cwd.as_deref());
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
    cfg: &PtyBackendConfig,
    vault: SecretVault,
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
    if adapter.label == "cursor" {
        if let Ok(home) = std::env::var("HOME") {
            let local_bin = format!("{home}/.local/bin");
            let path = std::env::var("PATH").unwrap_or_default();
            cmd.env("PATH", format!("{local_bin}:{path}"));
        }
    }
    apply_cli_auth_env(&mut cmd, cfg, &vault);
    if let Some(cwd) = &adapter.cwd {
        let p = Path::new(cwd);
        if p.is_dir() {
            cmd.current_dir(p);
        } else {
            return Err(Error::agent(format!(
                "CLI 工作目录不存在: {cwd}（请检查好友 cwd 或从项目根目录启动 seven-chat-agent-server）"
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
    std::env::var("SEVEN_CHAT_AGENT_CLI_STREAM_CHUNK")
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

/// 私聊默认工作区（Agent 构造时用）；群聊在 `send` 时按 `ChatContext` 重算。
fn resolve_pty_cwd(cfg: &PtyBackendConfig, friend_id: &str) -> Result<String> {
    resolve_cli_workspace(cfg, friend_id, None, None, None)
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


