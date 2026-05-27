//! 好友 CLI / 工蜂实例判定（产品模型）。

use crate::domain::{BackendKind, Friend, PtyBackendConfig};
use crate::store::SecretVault;

/// 外部 CLI 每轮独立 `exec`（默认）。
pub const CLI_SESSION_ONESHOT: &str = "oneshot";
/// Codex：`codex exec resume <thread_id>` 续接同一线程。
pub const CLI_SESSION_RESUME: &str = "resume";

pub const CODEX_SANDBOX_READ_ONLY: &str = "read-only";
pub const CODEX_SANDBOX_WORKSPACE_WRITE: &str = "workspace-write";
pub const CODEX_SANDBOX_DANGER: &str = "danger-full-access";
/// honeycomb 默认：可写工作区（Codex `exec` 自身默认是 read-only）。
pub const CODEX_SANDBOX_DEFAULT: &str = CODEX_SANDBOX_WORKSPACE_WRITE;

pub fn resolve_codex_sandbox_mode(cfg: &PtyBackendConfig) -> &'static str {
    match cfg.cli_sandbox_mode.as_deref() {
        Some(CODEX_SANDBOX_READ_ONLY) => CODEX_SANDBOX_READ_ONLY,
        Some(CODEX_SANDBOX_DANGER) => CODEX_SANDBOX_DANGER,
        Some(CODEX_SANDBOX_WORKSPACE_WRITE) | None => CODEX_SANDBOX_WORKSPACE_WRITE,
        Some(other) if other.trim().is_empty() => CODEX_SANDBOX_DEFAULT,
        Some(_) => CODEX_SANDBOX_WORKSPACE_WRITE,
    }
}

/// 外部 CLI 使用的 API Key 环境变量名（子进程注入）。
pub fn cli_api_key_env_var(preset: &str) -> Option<&'static str> {
    match preset {
        "cursor" => Some("CURSOR_API_KEY"),
        "codex-exec" => Some("OPENAI_API_KEY"),
        "claude" => Some("ANTHROPIC_API_KEY"),
        _ => None,
    }
}

/// 将 `cli_api_key` 写入 vault，并设置 `cli_api_key_ref`（外部 CLI 好友）。
pub fn persist_pty_cli_api_key(
    vault: &SecretVault,
    friend_id: &str,
    cfg: &mut PtyBackendConfig,
) -> crate::Result<()> {
    let Some(key) = cfg
        .cli_api_key
        .take()
        .filter(|s| !s.trim().is_empty())
    else {
        return Ok(());
    };
    if !is_external_cli_preset(cfg) {
        return Ok(());
    }
    let secret_ref = format!("vault:cli-auth-{friend_id}");
    vault.set(&secret_ref, key.trim())?;
    cfg.cli_api_key_ref = Some(secret_ref);
    Ok(())
}

/// 向即将 spawn 的外部 CLI 子进程注入 API Key 环境变量。
pub fn apply_cli_auth_env(
    cmd: &mut tokio::process::Command,
    cfg: &PtyBackendConfig,
    vault: &SecretVault,
) {
    let preset = cfg.preset.as_deref().unwrap_or("");
    let Some(var) = cli_api_key_env_var(preset) else {
        return;
    };
    let Some(ref secret_ref) = cfg.cli_api_key_ref else {
        return;
    };
    let Some(key) = vault.get(secret_ref) else {
        return;
    };
    cmd.env(var, key);
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct CliAuthProbe {
    pub preset: String,
    pub authenticated: bool,
    pub detail: String,
    pub api_key_configured: bool,
}

/// 探测外部 CLI 登录状态（供 Web 展示；不返回密钥）。
pub async fn probe_external_cli_auth(
    preset: &str,
    cmd: &str,
    cfg: &PtyBackendConfig,
    vault: &SecretVault,
) -> CliAuthProbe {
    let api_key_configured = cfg
        .cli_api_key_ref
        .as_ref()
        .is_some_and(|r| vault.get(r).is_some());
    let mut status = CliAuthProbe {
        preset: preset.into(),
        authenticated: false,
        detail: String::new(),
        api_key_configured,
    };
    match preset {
        "cursor" => {
            let out = tokio::process::Command::new(cmd)
                .arg("status")
                .output()
                .await;
            match out {
                Ok(o) => {
                    let text = String::from_utf8_lossy(&o.stdout);
                    let err = String::from_utf8_lossy(&o.stderr);
                    let combined = format!("{text}{err}");
                    status.authenticated =
                        combined.contains("Logged in") || combined.contains("logged in");
                    status.detail = combined.trim().to_string();
                    if !status.authenticated && api_key_configured {
                        status.authenticated = true;
                        status.detail = "已配置 CURSOR_API_KEY（vault）".into();
                    }
                }
                Err(e) => status.detail = format!("无法执行 {cmd} status: {e}"),
            }
        }
        "codex-exec" => {
            let out = tokio::process::Command::new(cmd)
                .args(["login", "status"])
                .output()
                .await;
            match out {
                Ok(o) => {
                    let text = format!(
                        "{}{}",
                        String::from_utf8_lossy(&o.stdout),
                        String::from_utf8_lossy(&o.stderr)
                    );
                    status.authenticated = text.contains("Logged in") || text.contains("logged in");
                    status.detail = text.trim().to_string();
                    if !status.authenticated && api_key_configured {
                        status.authenticated = true;
                        status.detail = "已配置 OPENAI_API_KEY（vault）".into();
                    }
                }
                Err(e) => status.detail = format!("无法执行 codex login status: {e}"),
            }
        }
        "claude" => {
            let out = tokio::process::Command::new(cmd)
                .args(["auth", "status"])
                .output()
                .await;
            match out {
                Ok(o) => {
                    let text = format!(
                        "{}{}",
                        String::from_utf8_lossy(&o.stdout),
                        String::from_utf8_lossy(&o.stderr)
                    );
                    status.authenticated = text.contains("logged in")
                        || text.contains("Logged in")
                        || text.contains("authenticated");
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
        }
        _ => {
            status.detail = if api_key_configured {
                status.authenticated = true;
                "已配置 API Key（vault）".into()
            } else {
                "请配置 API Key 或在服务器上完成 CLI 登录".into()
            };
        }
    }
    status
}

pub fn clear_pty_cli_api_key(vault: &SecretVault, cfg: &mut PtyBackendConfig) -> crate::Result<()> {
    if let Some(ref secret_ref) = cfg.cli_api_key_ref {
        vault.delete(secret_ref).ok();
    }
    cfg.cli_api_key_ref = None;
    cfg.cli_api_key = None;
    Ok(())
}

pub fn pty_cli_session_is_resume(cfg: &PtyBackendConfig) -> bool {
    cfg.cli_session_mode.as_deref() == Some(CLI_SESSION_RESUME)
}

pub fn resolve_cli_session_id(cfg: &PtyBackendConfig) -> Option<&str> {
    cfg.cli_session_id.as_deref().filter(|s| !s.trim().is_empty())
}

/// Claude `claude -p` 参数（续接时 `--resume <session_id>`）。
pub fn claude_print_args(session_id: Option<&str>) -> Vec<String> {
    let mut args = vec!["-p".into(), "--output-format".into(), "json".into()];
    if let Some(id) = session_id.filter(|s| !s.trim().is_empty()) {
        args.push("--resume".into());
        args.push(id.trim().to_string());
    }
    args
}

/// Cursor `agent -p` 参数（续接时 `--resume <chat_id>`）。
pub fn cursor_agent_args(workspace: Option<&str>, session_id: Option<&str>) -> Vec<String> {
    let mut args = vec![
        "-p".into(),
        "--trust".into(),
        "--output-format".into(),
        "text".into(),
    ];
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

/// 外部 CLI oneshot / resume  argv（不含 prompt）。
pub fn external_cli_argv(
    preset: &str,
    session_id: Option<&str>,
    workspace: Option<&str>,
    sandbox_mode: &str,
) -> Vec<String> {
    match preset {
        "codex-exec" => codex_exec_args(session_id, sandbox_mode),
        "cursor" => cursor_agent_args(workspace, session_id),
        "claude" => claude_print_args(session_id),
        _ => vec![],
    }
}

/// 从 `claude -p --output-format json` 的 JSONL/JSON 行解析 `session_id`。
pub fn parse_claude_session_id_from_output(buf: &[u8]) -> Option<String> {
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

/// Cursor 续接模式且尚无 chat id 时，调用 `agent create-chat` 预分配会话。
pub async fn ensure_cursor_chat_session(
    cmd: &str,
    cfg: &mut PtyBackendConfig,
    store: &crate::store::SqliteStore,
    friend_id: &str,
) -> crate::Result<()> {
    if cfg.preset.as_deref() != Some("cursor") || !pty_cli_session_is_resume(cfg) {
        return Ok(());
    }
    if resolve_cli_session_id(cfg).is_some() {
        return Ok(());
    }
    let out = tokio::process::Command::new(cmd)
        .arg("create-chat")
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .output()
        .await
        .map_err(|e| crate::Error::agent(format!("agent create-chat: {e}")))?;
    let id = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if id.is_empty() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(crate::Error::agent(format!(
            "agent create-chat 未返回 chat id: {}",
            err.trim()
        )));
    }
    store.patch_friend_cli_session_id(friend_id, Some(id.clone())).await?;
    cfg.cli_session_id = Some(id);
    Ok(())
}

/// 构建 `codex exec` / `codex exec resume <id>` 的参数（不含 prompt）。
#[cfg(test)]
mod session_tests {
    use super::*;

    #[test]
    fn codex_exec_args_without_thread() {
        assert_eq!(
            codex_exec_args(None, CODEX_SANDBOX_WORKSPACE_WRITE),
            vec![
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "workspace-write",
                "--color",
                "never",
                "--json"
            ]
        );
    }

    #[test]
    fn codex_exec_args_with_resume() {
        assert_eq!(
            codex_exec_args(Some("tid-1"), CODEX_SANDBOX_WORKSPACE_WRITE),
            vec![
                "exec",
                "resume",
                "tid-1",
                "--skip-git-repo-check",
                "--full-auto",
                "--json"
            ]
        );
    }

    #[test]
    fn codex_exec_args_read_only_resume() {
        assert_eq!(
            codex_exec_args(Some("tid-1"), CODEX_SANDBOX_READ_ONLY),
            vec![
                "exec",
                "resume",
                "tid-1",
                "--skip-git-repo-check",
                "--json"
            ]
        );
    }
}

/// 构建 `codex exec` / `codex exec resume <id>` 的参数（不含 prompt）。
pub fn codex_exec_args(thread_id: Option<&str>, sandbox_mode: &str) -> Vec<String> {
    let mut args = vec!["exec".into()];
    let resuming = thread_id.is_some_and(|s| !s.trim().is_empty());
    if let Some(tid) = thread_id.filter(|s| !s.trim().is_empty()) {
        args.push("resume".into());
        args.push(tid.trim().to_string());
    }
    args.push("--skip-git-repo-check".into());
    append_codex_sandbox_flags(&mut args, sandbox_mode, resuming);
    // `codex exec resume` 不接受 `--color`（仅顶层 `exec` 有该选项）。
    if !resuming {
        args.push("--color".into());
        args.push("never".into());
    }
    args.push("--json".into());
    args
}

fn append_codex_sandbox_flags(args: &mut Vec<String>, sandbox_mode: &str, resuming: bool) {
    match sandbox_mode {
        CODEX_SANDBOX_WORKSPACE_WRITE if resuming => {
            args.push("--full-auto".into());
        }
        CODEX_SANDBOX_WORKSPACE_WRITE => {
            args.push("--sandbox".into());
            args.push(CODEX_SANDBOX_WORKSPACE_WRITE.into());
        }
        CODEX_SANDBOX_DANGER if resuming => {
            args.push("--dangerously-bypass-approvals-and-sandbox".into());
        }
        CODEX_SANDBOX_DANGER => {
            args.push("--sandbox".into());
            args.push(CODEX_SANDBOX_DANGER.into());
        }
        CODEX_SANDBOX_READ_ONLY if !resuming => {
            args.push("--sandbox".into());
            args.push(CODEX_SANDBOX_READ_ONLY.into());
        }
        _ => {}
    }
}
use crate::runtime::{WORKER_BEE_CLI_BIN, WORKER_BEE_CLI_PRESET};

const EXTERNAL_CLI_PRESETS: &[&str] = &["claude", "codex-exec", "cursor"];

/// 是否为本机**外部 CLI**（claude / codex-exec 等），推理在子进程内完成，不经服务端 Provider。
pub fn uses_external_cli(friend: &Friend) -> bool {
    if friend.backend_kind != BackendKind::Pty {
        return false;
    }
    let cfg: PtyBackendConfig =
        serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
    is_external_cli_preset(&cfg)
}

/// 是否为 **Worker Bee（工蜂）** 实例（走 Provider API）；与外部 CLI 互斥。
pub fn uses_worker_bee(friend: &Friend) -> bool {
    match friend.backend_kind {
        BackendKind::Api => true,
        BackendKind::Pty => {
            let cfg: PtyBackendConfig =
                serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
            pty_preset_is_worker_bee(&cfg)
        }
        BackendKind::Assistant => true,
        BackendKind::Human => false,
    }
}

pub fn is_external_cli_preset(cfg: &PtyBackendConfig) -> bool {
    cfg.preset
        .as_deref()
        .is_some_and(|p| EXTERNAL_CLI_PRESETS.contains(&p))
}

pub fn pty_preset_is_worker_bee(cfg: &PtyBackendConfig) -> bool {
    if is_external_cli_preset(cfg) {
        return false;
    }
    if cfg.preset.as_deref() == Some(WORKER_BEE_CLI_PRESET) {
        return true;
    }
    if cfg.cmd == WORKER_BEE_CLI_BIN {
        return true;
    }
    // 仅当 preset 未指定时，用遗留工蜂字段推断（兼容旧数据）
    let preset_empty = cfg
        .preset
        .as_ref()
        .map(|s| s.trim().is_empty())
        .unwrap_or(true);
    if !preset_empty {
        return false;
    }
    cfg.skills_dir.as_ref().is_some_and(|s| !s.trim().is_empty())
        || cfg.memory_top_k.is_some()
        || !cfg.provider_id.trim().is_empty()
        || !cfg.model.trim().is_empty()
        || cfg.api_key_id.is_some()
}

fn clear_worker_bee_fields(cfg: &mut PtyBackendConfig) {
    cfg.provider_id.clear();
    cfg.model.clear();
    cfg.api_key_id = None;
    cfg.skills_dir = None;
    cfg.memory_top_k = None;
}

fn apply_external_cli_defaults(cfg: &mut PtyBackendConfig) {
    let preset = cfg.preset.as_deref().unwrap_or("claude");
    let (cmd, _) = match preset {
        "codex-exec" => ("codex", ""),
        "cursor" => ("agent", ""),
        "claude" => ("claude", ""),
        _ => return,
    };
    cfg.preset = Some(preset.into());
    if cfg.cmd.is_empty() {
        cfg.cmd = cmd.into();
    }
}

/// 保存时规范化 Pty 配置：尊重用户选的 preset，不把 Codex/Claude 改回工蜂。
pub fn normalize_pty_config(cfg: &mut PtyBackendConfig, is_builtin: bool) {
    if is_external_cli_preset(cfg) {
        clear_worker_bee_fields(cfg);
        apply_external_cli_defaults(cfg);
        return;
    }

    if pty_preset_is_worker_bee(cfg) {
        cfg.preset = Some(WORKER_BEE_CLI_PRESET.into());
        if cfg.cmd.is_empty() {
            cfg.cmd = resolve_worker_bee_executable();
        }
        if is_builtin {
            if cfg
                .skills_dir
                .as_ref()
                .map(|s| s.trim().is_empty())
                .unwrap_or(true)
            {
                cfg.skills_dir = Some(
                    std::env::var("HONEYCOMB_SKILLS_DIR")
                        .unwrap_or_else(|_| "data/skills".into()),
                );
            }
            if cfg.memory_top_k.is_none() {
                cfg.memory_top_k = Some(5);
            }
        }
        return;
    }

    // 内置好友且未选外部 CLI：默认工蜂
    if is_builtin {
        cfg.preset = Some(WORKER_BEE_CLI_PRESET.into());
        cfg.cmd = resolve_worker_bee_executable();
        if cfg
            .skills_dir
            .as_ref()
            .map(|s| s.trim().is_empty())
            .unwrap_or(true)
        {
            cfg.skills_dir = Some(
                std::env::var("HONEYCOMB_SKILLS_DIR").unwrap_or_else(|_| "data/skills".into()),
            );
        }
        if cfg.memory_top_k.is_none() {
            cfg.memory_top_k = Some(5);
        }
    }
}

fn path_if_executable(p: &std::path::Path) -> Option<String> {
    p.is_file().then(|| p.to_string_lossy().into_owned())
}

/// 解析 `worker-bee` 可执行路径（绝对路径优先，避免 `spawn worker-bee` ENOENT）。
pub fn resolve_worker_bee_executable() -> String {
    if let Ok(p) = std::env::var("HONEYCOMB_WORKER_BEE_BIN") {
        let t = p.trim();
        if !t.is_empty() {
            return t.to_string();
        }
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            if let Some(p) = path_if_executable(&dir.join(WORKER_BEE_CLI_BIN)) {
                return p;
            }
            for rel in ["debug/worker-bee", "release/worker-bee"] {
                if let Some(p) = path_if_executable(&dir.join(rel)) {
                    return p;
                }
            }
            let mut walk = dir.to_path_buf();
            for _ in 0..6 {
                for sub in ["target/debug/worker-bee", "target/release/worker-bee"] {
                    if let Some(p) = path_if_executable(&walk.join(sub)) {
                        return p;
                    }
                }
                if !walk.pop() {
                    break;
                }
            }
        }
    }

    if std::process::Command::new(WORKER_BEE_CLI_BIN)
        .arg("--help")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
    {
        return WORKER_BEE_CLI_BIN.into();
    }

    for rel in ["target/debug/worker-bee", "target/release/worker-bee"] {
        if let Some(p) = path_if_executable(std::path::Path::new(rel)) {
            return p;
        }
    }

    WORKER_BEE_CLI_BIN.into()
}

/// Cursor Agent CLI 可执行文件名（新版主命令为 `agent`，旧版为 `cursor-agent`）。
pub const CURSOR_AGENT_ALIASES: &[&str] = &["agent", "cursor-agent"];

/// 非交互 `agent -p` 参数（prompt 由 Pty 以最后一个参数追加）。
pub fn cursor_agent_oneshot_args(workspace: Option<&str>) -> Vec<String> {
    let mut args = vec![
        "-p".into(),
        "--trust".into(),
        "--output-format".into(),
        "text".into(),
    ];
    if let Some(w) = workspace.filter(|s| !s.trim().is_empty()) {
        args.push("--workspace".into());
        args.push(w.trim().to_string());
    }
    args
}

/// 解析 Cursor Agent 可执行路径（绝对路径优先，避免 honeycomb-server PATH 不含 `~/.local/bin`）。
pub fn resolve_cursor_agent_executable() -> String {
    if let Ok(p) = std::env::var("HONEYCOMB_CURSOR_AGENT_BIN") {
        let t = p.trim();
        if !t.is_empty() {
            return t.to_string();
        }
    }

    for name in CURSOR_AGENT_ALIASES {
        if cli_command_works(name) {
            return (*name).into();
        }
    }

    if let Ok(home) = std::env::var("HOME") {
        let home = std::path::PathBuf::from(home);
        for rel in [".local/bin/agent", ".local/bin/cursor-agent"] {
            let p = home.join(rel);
            if let Some(path) = path_if_executable(&p) {
                return path;
            }
        }
        if let Some(p) = find_cursor_agent_in_share(&home.join(".local/share/cursor-agent/versions")) {
            return p;
        }
    }

    "cursor-agent".into()
}

/// 启动 Cursor 好友前校验。
pub fn ensure_cursor_agent_executable() -> crate::Result<String> {
    let path = resolve_cursor_agent_executable();
    if std::path::Path::new(&path).is_file() || cli_command_works(&path) {
        return Ok(path);
    }
    Err(crate::Error::agent(
        "找不到 Cursor Agent CLI（尝试过 agent / cursor-agent）。请安装: \
         curl -fsSL https://cursor.com/install | bash ，\
         或将可执行文件路径写入环境变量 HONEYCOMB_CURSOR_AGENT_BIN",
    ))
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

/// 启动工蜂前校验；失败时给出可操作的错误说明。
pub fn ensure_worker_bee_executable() -> crate::Result<String> {
    let path = resolve_worker_bee_executable();
    if std::path::Path::new(&path).is_file()
        || std::process::Command::new(&path)
            .arg("--help")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
    {
        return Ok(path);
    }
    Err(crate::Error::agent(format!(
        "找不到 worker-bee 可执行文件（解析为「{path}」）。请执行: cargo build -p worker-bee-cli --bin worker-bee ，\
         或设置环境变量 HONEYCOMB_WORKER_BEE_BIN=/绝对路径/worker-bee"
    )))
}

/// 解析 Pty 预设；未配置时返回错误（避免静默回退到 `claude` 导致 spawn 失败难排查）。
pub fn resolve_pty_preset(cfg: &PtyBackendConfig) -> crate::Result<String> {
    if is_external_cli_preset(cfg) {
        return Ok(cfg.preset.clone().unwrap());
    }
    if pty_preset_is_worker_bee(cfg) {
        return Ok(WORKER_BEE_CLI_PRESET.into());
    }
    if let Some(p) = cfg.preset.as_ref().filter(|s| !s.trim().is_empty() && s.as_str() != "custom") {
        return Ok(p.clone());
    }
    Err(crate::Error::bad_request(
        "未配置 CLI 预设：请在好友编辑里选择 Codex CLI / Claude / Worker Bee 等并保存",
    ))
}

pub fn effective_pty_preset(cfg: &PtyBackendConfig) -> String {
    resolve_pty_preset(cfg).unwrap_or_else(|_| "claude".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::PtyBackendConfig;

    #[test]
    fn normalize_accepts_codex_exec_preset() {
        let v = serde_json::json!({ "preset": "codex-exec" });
        let mut cfg: PtyBackendConfig = serde_json::from_value(v).unwrap();
        assert_eq!(cfg.preset.as_deref(), Some("codex-exec"));
        normalize_pty_config(&mut cfg, false);
        assert_eq!(cfg.preset.as_deref(), Some("codex-exec"));
        assert_eq!(cfg.cmd, "codex");
    }

    #[test]
    fn worker_bee_cmd_does_not_override_codex_preset() {
        let v = serde_json::json!({
            "preset": "codex-exec",
            "cmd": "codex",
            "provider_id": "",
            "skills_dir": null
        });
        let mut cfg: PtyBackendConfig = serde_json::from_value(v).unwrap();
        normalize_pty_config(&mut cfg, false);
        assert_eq!(cfg.preset.as_deref(), Some("codex-exec"));
    }
}
