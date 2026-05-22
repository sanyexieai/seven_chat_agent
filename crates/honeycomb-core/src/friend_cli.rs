//! 好友 CLI / 工蜂实例判定（产品模型）。

use crate::domain::{BackendKind, Friend, PtyBackendConfig};
use crate::runtime::{WORKER_BEE_CLI_BIN, WORKER_BEE_CLI_PRESET};

/// 是否为本机**外部 CLI**（claude / codex-exec 等），推理在子进程内完成，不经服务端 Provider。
pub fn uses_external_cli(friend: &Friend) -> bool {
    if friend.backend_kind != BackendKind::Pty {
        return false;
    }
    let cfg: PtyBackendConfig =
        serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
    !pty_preset_is_worker_bee(&cfg)
}

/// 是否为 **Worker Bee（工蜂）CLI 实例**；其下的 Provider/API 仅用于配置该实例。
pub fn uses_worker_bee(friend: &Friend) -> bool {
    match friend.backend_kind {
        BackendKind::Api => true,
        BackendKind::Pty => {
            let cfg: PtyBackendConfig =
                serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
            friend.is_builtin || pty_preset_is_worker_bee(&cfg)
        }
        BackendKind::Assistant => true,
        BackendKind::Human => false,
    }
}

pub fn pty_preset_is_worker_bee(cfg: &PtyBackendConfig) -> bool {
    if cfg.preset.as_deref() == Some(WORKER_BEE_CLI_PRESET) {
        return true;
    }
    if cfg.cmd == WORKER_BEE_CLI_BIN {
        return true;
    }
    // 前端曾只保存 API/技能字段、漏写 preset 时仍视为工蜂实例。
    cfg.skills_dir.as_ref().is_some_and(|s| !s.trim().is_empty())
        || cfg.memory_top_k.is_some()
        || !cfg.provider_id.trim().is_empty()
        || !cfg.model.trim().is_empty()
        || cfg.api_key_id.is_some()
}

/// 规范化 Pty 配置：补全工蜂 preset，避免 `preset=null` 被当成外部 claude CLI。
pub fn normalize_pty_config(cfg: &mut PtyBackendConfig, is_builtin: bool) {
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

    // 与 honeycomb-server 同目录（`cargo run --bin honeycomb-server` 常见布局）
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

pub fn effective_pty_preset(cfg: &PtyBackendConfig) -> String {
    if pty_preset_is_worker_bee(cfg) {
        return WORKER_BEE_CLI_PRESET.into();
    }
    cfg.preset
        .clone()
        .filter(|s| !s.is_empty() && s != "custom")
        .unwrap_or_else(|| "claude".into())
}
