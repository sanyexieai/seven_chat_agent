//! 好友 CLI 与蜂巢平台的衔接（vault、store、Pty 配置规范化）。
//!
//! 统一驱动接口见独立 crate [`seven_chat_agent_cli`]。

use crate::domain::{BackendKind, Friend, PtyBackendConfig};
use crate::store::SecretVault;

pub use seven_chat_agent_cli::{
    api_key_env_var as cli_api_key_env_var, classify_pty_preset, driver_for_preset,
    exec_argv as external_cli_argv, is_worker_bee_preset, parse_session_id, prepare_resume_session,
    resume_session_likely_invalid, uses_codex_jsonl_stream, CliAuthProbe, CliDriver,
    CliLaunchConfig, CliSessionMode, CLI_SESSION_ONESHOT, CLI_SESSION_RESUME, CODEX_SANDBOX_DANGER,
    CODEX_SANDBOX_DEFAULT, CODEX_SANDBOX_READ_ONLY, CODEX_SANDBOX_WORKSPACE_WRITE,
    CURSOR_AGENT_ALIASES, EXTERNAL_CLI_PRESETS, PRESET_CODEX, PRESET_CURSOR, PRESET_WORKER_BEE,
    WORKER_BEE_CLI_BIN, WORKER_BEE_CLI_PRESET, resolve_codex_sandbox_mode,
};
pub use seven_chat_agent_cli::{ClaudeDriver, CodexDriver, CursorDriver, WorkerBeeDriver};

/// 从 Pty 好友配置构建 CLI 启动快照。
pub fn launch_from_pty(cfg: &PtyBackendConfig) -> CliLaunchConfig {
    CliLaunchConfig {
        preset: cfg.preset.clone().unwrap_or_default(),
        cmd: cfg.cmd.clone(),
        cli_session_mode: cfg.cli_session_mode.clone(),
        cli_session_id: cfg.cli_session_id.clone(),
        cli_sandbox_mode: cfg.cli_sandbox_mode.clone(),
    }
}

pub fn pty_execution_is_relay(cfg: &PtyBackendConfig) -> bool {
    cfg.execution_mode.as_deref() == Some("relay")
}

pub fn pty_relay_id(cfg: &PtyBackendConfig) -> Option<&str> {
    cfg.relay_id
        .as_deref()
        .filter(|s| !s.trim().is_empty())
}

/// 是否为服务端自动创建的 cli-workspaces 路径（不能作为 relay 远程 cwd）。
pub fn looks_like_server_cli_workspace(path: &str) -> bool {
    let t = path.trim();
    if t.is_empty() {
        return false;
    }
    t.contains("cli-workspaces")
}

/// CLI 工作目录：群聊用群共享目录（仅 local）；relay 由转发端按 friend_id 自行解析。
pub fn resolve_cli_workspace(
    cfg: &PtyBackendConfig,
    friend_id: &str,
    group_id: Option<&str>,
    group_cli_workspace: Option<&str>,
    member_local_path: Option<&str>,
) -> crate::Result<String> {
    if pty_execution_is_relay(cfg) {
        if let Some(p) = member_local_path.filter(|s| !s.trim().is_empty()) {
            return Ok(p.trim().to_string());
        }
        let rid = pty_relay_id(cfg).unwrap_or("?");
        return Ok(format!("@relay:{rid}/friends/{friend_id}"));
    }
    if let Some(gid) = group_id.filter(|s| !s.is_empty()) {
        if let Some(p) = member_local_path.filter(|s| !s.trim().is_empty()) {
            return crate::cli_workspace::ensure_at(p);
        }
        if let Some(ws) = group_cli_workspace {
            let t = ws.trim();
            if !t.is_empty() {
                return crate::cli_workspace::ensure_at(t);
            }
        }
        return crate::cli_workspace::ensure_for_group(gid);
    }
    resolve_cli_workspace_dm(cfg, friend_id)
}

fn resolve_cli_workspace_dm(cfg: &PtyBackendConfig, friend_id: &str) -> crate::Result<String> {
    if let Some(ref p) = cfg.cwd {
        let t = p.trim();
        if !t.is_empty() {
            return crate::cli_workspace::ensure_at(t);
        }
    }
    if let Ok(global) = std::env::var("SEVEN_CHAT_AGENT_CLI_CWD") {
        let t = global.trim();
        if !t.is_empty() {
            return crate::cli_workspace::ensure_at(t);
        }
    }
    if friend_id.is_empty() {
        return Err(crate::Error::Config(
            "pty friend id required to resolve default cli workspace".into(),
        ));
    }
    crate::cli_workspace::ensure_for_friend(friend_id)
}

pub fn pty_cli_session_is_resume(cfg: &PtyBackendConfig) -> bool {
    launch_from_pty(cfg).session_mode() == CliSessionMode::Resume
}

pub fn resolve_cli_session_id(cfg: &PtyBackendConfig) -> Option<&str> {
    cfg.cli_session_id
        .as_deref()
        .filter(|s| !s.trim().is_empty())
}

/// 是否为第三方本机 CLI 预设（`&PtyBackendConfig` 便捷封装）。
pub fn is_external_cli_preset(cfg: &PtyBackendConfig) -> bool {
    seven_chat_agent_cli::is_external_cli_preset(cfg.preset.as_deref())
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

/// 从 vault 解析外部 CLI API Key 环境变量（供本机 spawn 或远程转发任务使用）。
pub fn cli_auth_env_pairs(
    cfg: &PtyBackendConfig,
    vault: &SecretVault,
) -> Vec<(String, String)> {
    let preset = cfg.preset.as_deref().unwrap_or("");
    let Some(var) = cli_api_key_env_var(preset) else {
        return Vec::new();
    };
    let Some(ref secret_ref) = cfg.cli_api_key_ref else {
        return Vec::new();
    };
    let Some(key) = vault.get(secret_ref) else {
        return Vec::new();
    };
    vec![(var.to_string(), key)]
}

/// 向即将 spawn 的外部 CLI 子进程注入 API Key 环境变量。
pub fn apply_cli_auth_env(
    cmd: &mut tokio::process::Command,
    cfg: &PtyBackendConfig,
    vault: &SecretVault,
) {
    for (k, v) in cli_auth_env_pairs(cfg, vault) {
        cmd.env(k, v);
    }
}

/// OAuth / 鉴权探测用的可执行文件路径（解析 `agent` 别名与 `~/.local/bin`）。
pub fn resolve_external_cli_executable(
    preset: &str,
    cfg: &PtyBackendConfig,
) -> crate::Result<String> {
    let launch = launch_from_pty(cfg);
    seven_chat_agent_cli::ensure_executable(preset, &launch)
        .map_err(|e| crate::Error::agent(e.to_string()))
}

/// 按好友配置探测 CLI 鉴权：远程转发读 relay 上报，本机执行则在服务端探测。
pub async fn probe_friend_cli_auth(
    store: &crate::store::SqliteStore,
    hub: &crate::cli_relay::RelayHub,
    friend_id: &str,
) -> crate::Result<CliAuthProbe> {
    use crate::domain::{BackendKind, PtyBackendConfig};
    use crate::Error;

    let friend = store
        .get_friend(friend_id)
        .await?
        .ok_or_else(|| Error::not_found(format!("friend {friend_id}")))?;
    if friend.backend_kind != BackendKind::Pty {
        return Err(Error::bad_request("仅 Pty 好友支持 CLI 鉴权探测"));
    }
    let cfg: PtyBackendConfig =
        serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
    if !is_external_cli_preset(&cfg) {
        return Err(Error::bad_request("仅外部 CLI 好友支持鉴权探测"));
    }
    let preset = cfg.preset.clone().unwrap_or_default();

    if pty_execution_is_relay(&cfg) {
        let relay_id = pty_relay_id(&cfg).ok_or_else(|| {
            Error::bad_request("远程转发未选择在线节点（relay_id）")
        })?;
        if !hub.is_online(relay_id) {
            return Ok(CliAuthProbe {
                preset,
                authenticated: false,
                detail: format!(
                    "转发节点 {relay_id} 未在线，请在本机启动 seven-chat-agent-cli-relay"
                ),
                api_key_configured: relay_api_key_configured(&cfg, &store.vault),
            });
        }
        let api_key_configured = relay_api_key_configured(&cfg, &store.vault);
        if let Some(mut probe) = hub.auth_for_preset(relay_id, &preset) {
            probe.api_key_configured = api_key_configured;
            if api_key_configured && !probe.authenticated {
                probe.authenticated = true;
                if probe.detail.is_empty() {
                    probe.detail = "已配置 API Key（vault，将下发到远程）".into();
                }
            }
            let node = hub.node_name(relay_id).unwrap_or_else(|| relay_id.to_string());
            if !probe.detail.starts_with("远程节点") {
                probe.detail = format!("远程节点 {node}：{}", probe.detail);
            }
            return Ok(probe);
        }
        return Ok(CliAuthProbe {
            preset,
            authenticated: api_key_configured,
            detail: if api_key_configured {
                "已配置 API Key；转发节点尚未上报 CLI 登录状态，请更新 cli-relay 并重连".into()
            } else {
                format!(
                    "转发节点 {relay_id} 尚未上报登录状态。请在本机执行 agent login / codex login 后保持 cli-relay 连接"
                )
            },
            api_key_configured,
        });
    }

    Ok(probe_external_cli_auth(&preset, &cfg, &store.vault).await)
}

fn relay_api_key_configured(cfg: &PtyBackendConfig, vault: &SecretVault) -> bool {
    cfg.cli_api_key_ref
        .as_ref()
        .is_some_and(|r| vault.get(r).is_some())
}

/// 探测外部 CLI 登录状态（供 Web 展示；不返回密钥）。
pub async fn probe_external_cli_auth(
    preset: &str,
    cfg: &PtyBackendConfig,
    vault: &SecretVault,
) -> CliAuthProbe {
    let api_key_configured = cfg
        .cli_api_key_ref
        .as_ref()
        .is_some_and(|r| vault.get(r).is_some());
    let cmd = match resolve_external_cli_executable(preset, cfg) {
        Ok(path) => path,
        Err(e) => {
            return CliAuthProbe {
                preset: preset.to_string(),
                authenticated: false,
                detail: e.to_string(),
                api_key_configured,
            };
        }
    };
    seven_chat_agent_cli::probe_auth(preset, &cmd, api_key_configured).await
}

pub fn clear_pty_cli_api_key(vault: &SecretVault, cfg: &mut PtyBackendConfig) -> crate::Result<()> {
    if let Some(ref secret_ref) = cfg.cli_api_key_ref {
        vault.delete(secret_ref).ok();
    }
    cfg.cli_api_key_ref = None;
    cfg.cli_api_key = None;
    Ok(())
}

/// Cursor 续接模式且尚无 chat id 时预分配会话（并写入 store）。
pub async fn ensure_cursor_chat_session(
    cmd: &str,
    cfg: &mut PtyBackendConfig,
    store: &crate::store::SqliteStore,
    friend_id: &str,
) -> crate::Result<()> {
    if cfg.preset.as_deref() != Some(PRESET_CURSOR) || !pty_cli_session_is_resume(cfg) {
        return Ok(());
    }
    if resolve_cli_session_id(cfg).is_some() {
        return Ok(());
    }
    let launch = launch_from_pty(cfg);
    let id = prepare_resume_session(PRESET_CURSOR, &launch, cmd)
        .await
        .map_err(|e| crate::Error::agent(e.to_string()))?
        .ok_or_else(|| {
            crate::Error::agent("agent create-chat 未返回 chat id".to_string())
        })?;
    store.patch_friend_cli_session_id(friend_id, Some(id.clone())).await?;
    if let Ok(Some(ws)) = store.get_active_workspace(friend_id).await {
        let _ = store
            .patch_cli_session_native_id(&ws.id, crate::cli_tool::TOOL_CURSOR, Some(id.clone()))
            .await;
    }
    cfg.cli_session_id = Some(id);
    Ok(())
}

// ── 向后兼容别名 ──

pub fn claude_print_args(session_id: Option<&str>) -> Vec<String> {
    ClaudeDriver::print_args(session_id)
}

pub fn cursor_agent_args(workspace: Option<&str>, session_id: Option<&str>) -> Vec<String> {
    CursorDriver::agent_args(workspace, session_id)
}

pub fn codex_exec_args(thread_id: Option<&str>, sandbox_mode: &str) -> Vec<String> {
    CodexDriver::exec_args(thread_id, sandbox_mode)
}

pub fn parse_claude_session_id_from_output(buf: &[u8]) -> Option<String> {
    ClaudeDriver::parse_session_id_from_output(buf)
}

pub fn resolve_cursor_agent_executable() -> String {
    CursorDriver::resolve_executable(&CliLaunchConfig::default())
}

pub fn ensure_cursor_agent_executable() -> crate::Result<String> {
    let launch = CliLaunchConfig::default();
    CursorDriver::ensure_executable(&launch).map_err(|e| crate::Error::agent(e.to_string()))
}

pub fn resolve_worker_bee_executable() -> String {
    WorkerBeeDriver::resolve_executable()
}

pub fn ensure_worker_bee_executable() -> crate::Result<String> {
    WorkerBeeDriver::ensure_executable().map_err(|e| crate::Error::agent(e.to_string()))
}

pub fn uses_external_cli(friend: &Friend) -> bool {
    if friend.backend_kind != BackendKind::Pty {
        return false;
    }
    let cfg: PtyBackendConfig =
        serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
    is_external_cli_preset(&cfg)
}

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

pub fn pty_preset_is_worker_bee(cfg: &PtyBackendConfig) -> bool {
    if is_external_cli_preset(cfg) {
        return false;
    }
    if is_worker_bee_preset(cfg.preset.as_deref()) {
        return true;
    }
    if cfg.cmd == WORKER_BEE_CLI_BIN {
        return true;
    }
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
    let cmd = match preset {
        PRESET_CODEX => "codex",
        PRESET_CURSOR => "agent",
        seven_chat_agent_cli::PRESET_CLAUDE => "claude",
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
                    std::env::var("SEVEN_CHAT_AGENT_SKILLS_DIR")
                        .unwrap_or_else(|_| "data/skills".into()),
                );
            }
            if cfg.memory_top_k.is_none() {
                cfg.memory_top_k = Some(5);
            }
        }
        return;
    }

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
                std::env::var("SEVEN_CHAT_AGENT_SKILLS_DIR").unwrap_or_else(|_| "data/skills".into()),
            );
        }
        if cfg.memory_top_k.is_none() {
            cfg.memory_top_k = Some(5);
        }
    }
}

pub fn resolve_pty_preset(cfg: &PtyBackendConfig) -> crate::Result<String> {
    let has_wb = cfg.skills_dir.as_ref().is_some_and(|s| !s.trim().is_empty())
        || cfg.memory_top_k.is_some()
        || !cfg.provider_id.trim().is_empty()
        || !cfg.model.trim().is_empty()
        || cfg.api_key_id.is_some();
    classify_pty_preset(cfg.preset.as_deref(), &cfg.cmd, has_wb).ok_or_else(|| {
        crate::Error::bad_request(
            "未配置 CLI 预设：请在好友编辑里选择 Codex CLI / Claude / Worker Bee 等并保存",
        )
    })
}

pub fn effective_pty_preset(cfg: &PtyBackendConfig) -> String {
    resolve_pty_preset(cfg).unwrap_or_else(|_| seven_chat_agent_cli::PRESET_CLAUDE.into())
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
    fn relay_workspace_is_virtual_until_reported() {
        let cfg = PtyBackendConfig {
            execution_mode: Some("relay".into()),
            relay_id: Some("relay_abc".into()),
            ..Default::default()
        };
        assert_eq!(
            resolve_cli_workspace(&cfg, "friend-1", None, None, None).unwrap(),
            "@relay:relay_abc/friends/friend-1"
        );
    }

    #[test]
    fn relay_accepts_member_local_path() {
        let cfg = PtyBackendConfig {
            execution_mode: Some("relay".into()),
            ..Default::default()
        };
        assert_eq!(
            resolve_cli_workspace(&cfg, "f", None, None, Some("/remote/group-ws")).unwrap(),
            "/remote/group-ws"
        );
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
