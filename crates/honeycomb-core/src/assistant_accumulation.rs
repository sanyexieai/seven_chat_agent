//! 助理自动沉淀：备忘录 / 知识库 / 工具箱 的分类约定。

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
