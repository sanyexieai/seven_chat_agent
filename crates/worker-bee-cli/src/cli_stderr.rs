//! 外部 CLI stderr 致命错误判定（Codex / Cursor 等共用）。

pub fn is_cli_fatal_stderr(s: &str) -> bool {
    let lower = s.to_lowercase();
    lower.contains("not inside a trusted directory")
        || lower.contains("no such file or directory")
        || lower.contains("etimedout")
        || lower.contains("econnrefused")
        || lower.contains("enotfound")
        || lower.contains("[unavailable]")
        || lower.contains("error:")
        || lower.contains("failed")
}
