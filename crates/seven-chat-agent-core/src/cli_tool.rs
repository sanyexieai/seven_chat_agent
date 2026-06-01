//! Pty 预设 → CLI 工具名（工作区会话维度）。

pub const TOOL_CODEX: &str = "codex";
pub const TOOL_CLAUDE: &str = "claude";
pub const TOOL_CURSOR: &str = "cursor";

/// 外部 CLI 预设对应的会话工具；工蜂等返回 `None`。
pub fn tool_for_preset(preset: Option<&str>) -> Option<&'static str> {
    match preset.unwrap_or("").trim() {
        "codex-exec" | "codex" => Some(TOOL_CODEX),
        "claude" => Some(TOOL_CLAUDE),
        "cursor" => Some(TOOL_CURSOR),
        _ => None,
    }
}
