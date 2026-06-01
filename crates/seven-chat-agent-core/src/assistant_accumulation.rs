//! 助理自动沉淀：备忘录 / 知识库 / 工具箱 的分类约定。
//!
//! 写入分层见 [`crate::memory_record_policy`]：
//! - 观察备忘：其他会话里有信息量的用户发言（非寒暄、非重复）。
//! - 协助记录：可选流水账，默认关闭。
//! - 知识库：仅 LLM 提取/反思产出的可复用事实。

pub const MEMORY_KIND_MEMO: &str = "memo";
pub const MEMORY_KIND_KNOWLEDGE: &str = "knowledge";

/// 备忘录类（会话观察、代发摘要等）。
pub fn is_memo_kind(kind: &str) -> bool {
    matches!(
        kind,
        MEMORY_KIND_MEMO | "conversation_observe" | "group_turn"
    )
}

/// 知识库类（稳定事实、反思提炼等）。
pub fn is_knowledge_kind(kind: &str) -> bool {
    matches!(
        kind,
        MEMORY_KIND_KNOWLEDGE | "fact" | "preference" | "project" | "relation" | "lesson"
    )
}

/// LLM 抽取的记忆 kind 统一写入知识库。
pub fn normalize_extracted_kind(kind: &str) -> &'static str {
    if is_memo_kind(kind) {
        MEMORY_KIND_MEMO
    } else {
        MEMORY_KIND_KNOWLEDGE
    }
}

pub fn truncate_chars(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        return s.to_string();
    }
    let mut out: String = s.chars().take(max).collect();
    out.push('…');
    out
}

/// 面板展示用：根据内容前缀推断记忆来源（跨私聊/群聊会话）。
pub fn memory_source_label(content: &str) -> &'static str {
    let first = content.lines().next().unwrap_or("");
    if first.contains("[默认观察/") {
        return "会话观察";
    }
    if first.starts_with("[协助记录]") {
        return "协助回合";
    }
    if first.starts_with("[待办执行]") || first.starts_with("[空闲守护完成]") {
        return "后台任务";
    }
    if first.contains("代发") || first.contains("群聊:") {
        return "群协作";
    }
    "其他"
}

/// 从观察类记忆首行解析会话范围，如「私聊:小明」「群聊:研发群」。
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn memory_source_and_scope_labels() {
        assert_eq!(
            memory_source_label("[默认观察/私聊:小明] 用户:u\n内容:hi"),
            "会话观察"
        );
        assert_eq!(
            memory_scope_from_content("[默认观察/群聊:研发群] 用户:u\n内容:hi"),
            Some("群聊:研发群".into())
        );
    }
}

pub fn memory_scope_from_content(content: &str) -> Option<String> {
    let first = content.lines().next()?;
    let start = first.find("[默认观察/")?;
    let inner = first[start + "[默认观察/".len()..].trim_end_matches(']');
    if inner.is_empty() {
        None
    } else {
        Some(inner.to_string())
    }
}
