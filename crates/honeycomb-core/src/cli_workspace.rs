//! 为 Pty 后端（cli：claude code / cursor 等）准备隔离工作区：自动建目录，默认 `git init`。

use std::path::{Path, PathBuf};

use crate::{Error, Result};

/// 工作区根目录：`HONEYCOMB_CLI_WORKSPACE_ROOT`，否则 `{HONEYCOMB_DATA}/cli-workspaces`。
pub fn workspace_root() -> PathBuf {
    if let Ok(root) = std::env::var("HONEYCOMB_CLI_WORKSPACE_ROOT") {
        let t = root.trim();
        if !t.is_empty() {
            return PathBuf::from(t);
        }
    }
    let data = std::env::var("HONEYCOMB_DATA").unwrap_or_else(|_| "data".into());
    PathBuf::from(data).join("cli-workspaces")
}

pub fn default_path_for_friend(friend_id: &str) -> PathBuf {
    workspace_root().join(friend_id)
}

/// 默认 `true`；设 `HONEYCOMB_CLI_AUTO_GIT=0` 可关闭自动 `git init`。
pub fn auto_git_enabled() -> bool {
    match std::env::var("HONEYCOMB_CLI_AUTO_GIT")
        .unwrap_or_default()
        .to_lowercase()
        .as_str()
    {
        "0" | "false" | "no" | "off" => false,
        _ => true,
    }
}

/// 创建目录；若启用且尚无 `.git`，则执行 `git init -q`。
pub fn ensure_workspace(path: &Path, init_git: bool) -> Result<()> {
    std::fs::create_dir_all(path).map_err(Error::Io)?;
    if init_git && auto_git_enabled() && !path.join(".git").is_dir() {
        match std::process::Command::new("git")
            .args(["init", "-q"])
            .current_dir(path)
            .status()
        {
            Ok(status) if status.success() => {
                tracing::info!(path = %path.display(), "cli workspace: git init");
            }
            Ok(status) => {
                tracing::warn!(
                    path = %path.display(),
                    code = ?status.code(),
                    "cli workspace: git init failed"
                );
            }
            Err(e) => {
                tracing::warn!(path = %path.display(), err = %e, "cli workspace: git not available");
            }
        }
    }
    Ok(())
}

/// 将路径规范为绝对路径。`codex exec -C` 若收到相对路径会相对**进程 cwd** 解析，
/// 与 honeycomb-server 启动目录不一致时会 `No such file or directory (os error 2)`。
fn absolutize(path: &Path) -> Result<PathBuf> {
    if path.is_absolute() {
        return path.canonicalize().map_err(Error::Io);
    }
    let base = std::env::current_dir().map_err(Error::Io)?;
    base.join(path).canonicalize().map_err(Error::Io)
}

/// 每位 CLI 好友的默认工作区：`{workspace_root}/{friend_id}`。
pub fn ensure_for_friend(friend_id: &str) -> Result<String> {
    let path = default_path_for_friend(friend_id);
    ensure_workspace(&path, true)?;
    Ok(absolutize(&path)?.to_string_lossy().into_owned())
}

/// 用户或 `HONEYCOMB_CLI_CWD` 指定的目录：同样自动建目录并按需 init git。
pub fn ensure_at(path: &str) -> Result<String> {
    let p = PathBuf::from(path.trim());
    ensure_workspace(&p, true)?;
    Ok(absolutize(&p)?.to_string_lossy().into_owned())
}
