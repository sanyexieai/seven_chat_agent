//! 好友 CLI / 工蜂实例判定（产品模型）。

use crate::domain::{BackendKind, Friend, PtyBackendConfig};
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
        "cursor" => ("cursor-agent", ""),
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
