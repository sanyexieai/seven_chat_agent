//! 转发端工作区约定：根目录由本机决定，按 friend_id / group_id 分子目录。

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

/// 转发端工作区根目录。
///
/// 优先级：`SEVEN_CHAT_AGENT_RELAY_WORKSPACE_ROOT` →
/// `~/.local/share/seven-chat-agent/cli-workspaces`。
pub fn workspace_root() -> PathBuf {
    if let Ok(root) = std::env::var("SEVEN_CHAT_AGENT_RELAY_WORKSPACE_ROOT") {
        let t = root.trim();
        if !t.is_empty() {
            return PathBuf::from(t);
        }
    }
    home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".local/share/seven-chat-agent/cli-workspaces")
}

fn home_dir() -> Option<PathBuf> {
    std::env::var("HOME")
        .ok()
        .or_else(|| std::env::var("USERPROFILE").ok())
        .map(PathBuf::from)
}

pub fn workspace_root_string() -> String {
    absolutize(&workspace_root())
        .unwrap_or_else(|_| workspace_root())
        .to_string_lossy()
        .into_owned()
}

/// 解析单次 RunJob 的 cwd：override → 群目录 → 好友目录。
pub fn resolve_job_cwd(
    friend_id: &str,
    group_id: Option<&str>,
    cwd_override: Option<&str>,
) -> Result<PathBuf> {
    if let Some(o) = cwd_override.map(str::trim).filter(|s| !s.is_empty()) {
        return ensure_at(o);
    }
    if let Some(gid) = group_id.map(str::trim).filter(|s| !s.is_empty()) {
        let p = workspace_root().join("groups").join(gid);
        return ensure_at_path(&p);
    }
    let p = workspace_root().join("friends").join(friend_id);
    ensure_at_path(&p)
}

/// 上报给服务端的约定路径（不保证目录已创建）。
pub fn friend_workspace_path(root: &str, friend_id: &str) -> String {
    format!(
        "{}/friends/{}",
        root.trim_end_matches('/'),
        friend_id.trim()
    )
}

fn ensure_at(path: &str) -> Result<PathBuf> {
    ensure_at_path(Path::new(path.trim()))
}

fn ensure_at_path(path: &Path) -> Result<PathBuf> {
    std::fs::create_dir_all(path).with_context(|| format!("create workspace {}", path.display()))?;
    if auto_git_enabled() && !path.join(".git").is_dir() {
        let _ = std::process::Command::new("git")
            .args(["init", "-q"])
            .current_dir(path)
            .status();
    }
    absolutize(path)
}

fn auto_git_enabled() -> bool {
    match std::env::var("SEVEN_CHAT_AGENT_RELAY_AUTO_GIT")
        .or_else(|_| std::env::var("SEVEN_CHAT_AGENT_CLI_AUTO_GIT"))
        .unwrap_or_default()
        .to_lowercase()
        .as_str()
    {
        "0" | "false" | "no" | "off" => false,
        _ => true,
    }
}

fn absolutize(path: &Path) -> Result<PathBuf> {
    if path.is_absolute() {
        return path.canonicalize().with_context(|| path.display().to_string());
    }
    let base = std::env::current_dir().context("current_dir")?;
    base.join(path)
        .canonicalize()
        .with_context(|| path.display().to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn friend_path_under_root() {
        assert_eq!(
            friend_workspace_path("/tmp/ws", "abc"),
            "/tmp/ws/friends/abc"
        );
    }
}
