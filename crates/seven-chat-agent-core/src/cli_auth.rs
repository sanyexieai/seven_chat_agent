//! 外部 CLI OAuth 登录（服务器侧启动 `agent login` / `codex login` 等，供 Web 展示链接）。

use std::process::Stdio;
use std::sync::Arc;
use std::time::{Duration, Instant};

use dashmap::DashMap;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::Mutex;

use crate::friend_cli::{probe_external_cli_auth, resolve_cursor_agent_executable};
use crate::store::{SecretVault, SqliteStore};
use crate::{Error, Result};

const OAUTH_TIMEOUT: Duration = Duration::from_secs(15 * 60);

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CliOAuthPhase {
    Idle,
    Pending,
    Succeeded,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct CliOAuthSnapshot {
    pub phase: CliOAuthPhase,
    pub auth_url: Option<String>,
    pub user_code: Option<String>,
    pub instructions: String,
    pub message: String,
}

impl Default for CliOAuthSnapshot {
    fn default() -> Self {
        Self {
            phase: CliOAuthPhase::Idle,
            auth_url: None,
            user_code: None,
            instructions: String::new(),
            message: String::new(),
        }
    }
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct CliAuthStatus {
    pub preset: String,
    pub authenticated: bool,
    pub detail: String,
    pub api_key_configured: bool,
    pub oauth_pending: bool,
    pub oauth_phase: CliOAuthPhase,
    pub oauth_url: Option<String>,
    pub oauth_user_code: Option<String>,
    pub oauth_instructions: Option<String>,
    pub oauth_message: Option<String>,
}

struct OAuthRun {
    child: Arc<Mutex<Option<tokio::process::Child>>>,
    started_at: Instant,
}

struct OAuthSession {
    preset: String,
    cmd: String,
    phase: CliOAuthPhase,
    auth_url: Option<String>,
    user_code: Option<String>,
    instructions: String,
    message: String,
    run: Option<OAuthRun>,
}

pub struct CliOAuthManager {
    sessions: Arc<DashMap<String, OAuthSession>>,
}

impl CliOAuthManager {
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(DashMap::new()),
        }
    }

    pub fn snapshot(&self, friend_id: &str) -> CliOAuthSnapshot {
        self.sessions
            .get(friend_id)
            .map(|s| CliOAuthSnapshot {
                phase: s.phase,
                auth_url: s.auth_url.clone(),
                user_code: s.user_code.clone(),
                instructions: s.instructions.clone(),
                message: s.message.clone(),
            })
            .unwrap_or_default()
    }

    pub async fn full_status(
        &self,
        store: &SqliteStore,
        friend_id: &str,
    ) -> Result<CliAuthStatus> {
        let base = store.probe_friend_cli_auth(friend_id).await?;
        let snap = self.snapshot(friend_id);
        Ok(merge_auth_status(base, snap))
    }

    pub async fn start(
        &self,
        store: &SqliteStore,
        friend_id: &str,
    ) -> Result<CliOAuthSnapshot> {
        if self
            .sessions
            .get(friend_id)
            .is_some_and(|s| s.phase == CliOAuthPhase::Pending)
        {
            return Err(Error::bad_request("已有进行中的 OAuth 登录，请先完成或取消"));
        }

        let (preset, cmd, cfg) = load_external_cli(store, friend_id).await?;
        self.cancel(friend_id).await;

        let mut session = OAuthSession {
            preset: preset.clone(),
            cmd: cmd.clone(),
            phase: CliOAuthPhase::Pending,
            auth_url: None,
            user_code: None,
            instructions: oauth_instructions(&preset),
            message: "正在启动登录…".into(),
            run: None,
        };

        let (mut command, use_device_auth) = build_login_command(&preset, &cmd)?;
        if preset == "cursor" {
            if let Ok(home) = std::env::var("HOME") {
                let path = std::env::var("PATH").unwrap_or_default();
                command.env("PATH", format!("{home}/.local/bin:{path}"));
            }
            command.env("NO_OPEN_BROWSER", "1");
        }

        let mut child = command
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| Error::agent(format!("启动 {cmd} 登录失败: {e}")))?;

        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        let child_handle = Arc::new(Mutex::new(Some(child)));
        session.run = Some(OAuthRun {
            child: child_handle.clone(),
            started_at: Instant::now(),
        });
        self.sessions.insert(friend_id.to_string(), session);

        let sessions = self.sessions.clone();
        let fid = friend_id.to_string();
        let vault = store.vault.clone();
        let preset_bg = preset.clone();
        let cmd_bg = cmd.clone();

        tokio::spawn(async move {
            read_login_output(&sessions, &fid, stdout, stderr, use_device_auth).await;
            finish_login(
                &sessions,
                &fid,
                &preset_bg,
                &cmd_bg,
                &cfg,
                &vault,
                child_handle,
            )
            .await;
        });

        Ok(self.snapshot(friend_id))
    }

    pub async fn cancel(&self, friend_id: &str) -> Result<()> {
        if let Some(mut session) = self.sessions.get_mut(friend_id) {
            if let Some(run) = session.run.take() {
                if let Some(mut child) = run.child.lock().await.take() {
                    let _ = child.kill().await;
                }
            }
            if session.phase == CliOAuthPhase::Pending {
                session.phase = CliOAuthPhase::Cancelled;
                session.message = "已取消".into();
            }
        }
        Ok(())
    }

    pub async fn logout(
        &self,
        store: &SqliteStore,
        friend_id: &str,
    ) -> Result<CliAuthStatus> {
        self.cancel(friend_id).await?;
        let (preset, cmd, _) = load_external_cli(store, friend_id).await?;
        run_logout(&preset, &cmd).await?;
        Ok(self.full_status(store, friend_id).await?)
    }
}

fn merge_auth_status(
    mut base: crate::friend_cli::CliAuthProbe,
    snap: CliOAuthSnapshot,
) -> CliAuthStatus {
    let oauth_pending = snap.phase == CliOAuthPhase::Pending;
    if oauth_pending {
        base.authenticated = false;
    } else if snap.phase == CliOAuthPhase::Succeeded {
        base.authenticated = true;
        if base.detail.is_empty() {
            base.detail = snap.message.clone();
        }
    }
    CliAuthStatus {
        preset: base.preset,
        authenticated: base.authenticated,
        detail: base.detail,
        api_key_configured: base.api_key_configured,
        oauth_pending,
        oauth_phase: snap.phase,
        oauth_url: snap.auth_url,
        oauth_user_code: snap.user_code,
        oauth_instructions: if snap.instructions.is_empty() {
            None
        } else {
            Some(snap.instructions)
        },
        oauth_message: if snap.message.is_empty() {
            None
        } else {
            Some(snap.message)
        },
    }
}

async fn load_external_cli(
    store: &SqliteStore,
    friend_id: &str,
) -> Result<(String, String, crate::domain::PtyBackendConfig)> {
    let friend = store
        .get_friend(friend_id)
        .await?
        .ok_or_else(|| Error::not_found(format!("friend {friend_id}")))?;
    let cfg: crate::domain::PtyBackendConfig =
        serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
    if !crate::friend_cli::is_external_cli_preset(&cfg) {
        return Err(Error::bad_request("仅外部 CLI 好友支持 OAuth"));
    }
    let preset = cfg.preset.clone().unwrap();
    let cmd = resolve_cli_cmd(&preset, &cfg);
    Ok((preset, cmd, cfg))
}

fn resolve_cli_cmd(preset: &str, cfg: &crate::domain::PtyBackendConfig) -> String {
    if !cfg.cmd.is_empty() {
        return cfg.cmd.clone();
    }
    match preset {
        "cursor" => resolve_cursor_agent_executable(),
        "codex-exec" => "codex".into(),
        "claude" => "claude".into(),
        _ => cfg.cmd.clone(),
    }
}

fn oauth_instructions(preset: &str) -> String {
    match preset {
        "cursor" => "在浏览器打开下方链接，使用 Cursor 账号登录（登录态保存在 seven-chat-agent-server 所在机器）。".into(),
        "codex-exec" => "在浏览器打开链接并输入一次性设备码（登录态保存在服务器 ~/.codex）。".into(),
        "claude" => "在浏览器打开下方链接完成 Anthropic 登录（登录态保存在服务器）。".into(),
        _ => "在浏览器完成 OAuth 授权。".into(),
    }
}

fn build_login_command(preset: &str, cmd: &str) -> Result<(Command, bool)> {
    let mut c = Command::new(cmd);
    let device_auth = match preset {
        "cursor" => {
            c.arg("login");
            false
        }
        "codex-exec" => {
            c.args(["login", "--device-auth"]);
            true
        }
        "claude" => {
            c.args(["auth", "login"]);
            false
        }
        _ => return Err(Error::bad_request(format!("预设 {preset} 不支持 OAuth"))),
    };
    Ok((c, device_auth))
}

async fn run_logout(preset: &str, cmd: &str) -> Result<()> {
    let mut c = Command::new(cmd);
    match preset {
        "cursor" => {
            c.arg("logout");
        }
        "codex-exec" => {
            c.arg("logout");
        }
        "claude" => {
            c.args(["auth", "logout"]);
        }
        _ => return Ok(()),
    }
    let out = c
        .output()
        .await
        .map_err(|e| Error::agent(format!("{cmd} logout: {e}")))?;
    if !out.status.success() {
        let text = format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        );
        return Err(Error::agent(format!("登出失败: {}", text.trim())));
    }
    Ok(())
}

async fn read_login_output(
    sessions: &Arc<DashMap<String, OAuthSession>>,
    friend_id: &str,
    stdout: Option<tokio::process::ChildStdout>,
    stderr: Option<tokio::process::ChildStderr>,
    device_auth: bool,
) {
    let mut acc = String::new();
    if let Some(out) = stdout {
        let mut lines = BufReader::new(out).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            acc.push_str(&line);
            acc.push('\n');
            apply_parsed_login_line(sessions, friend_id, &line, device_auth);
        }
    }
    if let Some(err) = stderr {
        let mut lines = BufReader::new(err).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            acc.push_str(&line);
            acc.push('\n');
            apply_parsed_login_line(sessions, friend_id, &line, device_auth);
        }
    }
    if let Some(mut s) = sessions.get_mut(friend_id) {
        if s.auth_url.is_none() {
            apply_parsed_login_line(sessions, friend_id, &acc, device_auth);
        }
        if s.phase == CliOAuthPhase::Pending && s.message == "正在启动登录…" {
            s.message = if s.auth_url.is_some() || s.user_code.is_some() {
                "等待你在浏览器中完成授权…".into()
            } else {
                "等待 CLI 输出登录链接…".into()
            };
        }
    }
}

fn apply_parsed_login_line(
    sessions: &Arc<DashMap<String, OAuthSession>>,
    friend_id: &str,
    line: &str,
    device_auth: bool,
) {
    let plain = strip_ansi(line);
    if let Some(url) = extract_https_url(&plain) {
        if let Some(mut s) = sessions.get_mut(friend_id) {
            if s.auth_url.is_none() {
                s.auth_url = Some(url);
            }
        }
    }
    if device_auth {
        if let Some(code) = extract_device_code(&plain) {
            if let Some(mut s) = sessions.get_mut(friend_id) {
                s.user_code = Some(code);
            }
        }
    }
}

async fn finish_login(
    sessions: &Arc<DashMap<String, OAuthSession>>,
    friend_id: &str,
    preset: &str,
    cmd: &str,
    cfg: &crate::domain::PtyBackendConfig,
    vault: &SecretVault,
    child_handle: Arc<Mutex<Option<tokio::process::Child>>>,
) {
    let mut exit_ok = false;
    let mut wait_err = None;
    if let Some(mut child) = child_handle.lock().await.take() {
        match tokio::time::timeout(OAUTH_TIMEOUT, child.wait()).await {
            Ok(Ok(status)) => exit_ok = status.success(),
            Ok(Err(e)) => wait_err = Some(e.to_string()),
            Err(_) => {
                let _ = child.kill().await;
                wait_err = Some("登录超时（15 分钟）".into());
            }
        }
    }

    let probed = probe_external_cli_auth(preset, cmd, cfg, vault).await;
    if let Some(mut s) = sessions.get_mut(friend_id) {
        s.run = None;
        if s.phase == CliOAuthPhase::Cancelled {
            return;
        }
        if probed.authenticated {
            s.phase = CliOAuthPhase::Succeeded;
            s.message = "OAuth 登录成功".into();
        } else if exit_ok {
            s.phase = CliOAuthPhase::Succeeded;
            s.message = "登录进程已结束".into();
        } else {
            s.phase = CliOAuthPhase::Failed;
            s.message = wait_err
                .unwrap_or_else(|| probed.detail.clone());
            if s.message.is_empty() {
                s.message = "登录未完成或失败".into();
            }
        }
    }
}

fn strip_ansi(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\x1b' {
            if chars.peek() == Some(&'[') {
                chars.next();
                for ch in chars.by_ref() {
                    if ch.is_ascii_alphabetic() {
                        break;
                    }
                }
            }
            continue;
        }
        out.push(c);
    }
    out
}

fn extract_https_url(s: &str) -> Option<String> {
    let start = s.find("https://")?;
    let rest = &s[start..];
    let end = rest
        .find(|c: char| c.is_whitespace() || c == ')' || c == ']' || c == '"')
        .unwrap_or(rest.len());
    let url = rest[..end].trim();
    if url.len() > 12 {
        Some(url.to_string())
    } else {
        None
    }
}

/// Codex device-auth 一次性码形如 `ABCD-EFGH12`。
fn extract_device_code(s: &str) -> Option<String> {
    for word in s.split_whitespace() {
        let w = word.trim_matches(|c: char| !c.is_alphanumeric() && c != '-');
        if w.len() >= 8
            && w.contains('-')
            && w.chars().all(|c| c.is_ascii_alphanumeric() || c == '-')
        {
            return Some(w.to_string());
        }
    }
    None
}
