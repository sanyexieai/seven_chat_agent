use crate::context::JudgeRequest;

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        return s.to_string();
    }
    let mut t: String = s.chars().take(max).collect();
    t.push('…');
    t
}

/// 构建 LLM judge 用户 prompt。
pub fn build_llm_prompt(req: &JudgeRequest) -> String {
    let history_excerpt = req
        .history
        .iter()
        .rev()
        .take(6)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .map(|m| format!("[{}]: {}", m.sender_name, truncate(&m.content, 120)))
        .collect::<Vec<_>>()
        .join("\n");
    let personality = req.member.personality.as_deref().unwrap_or("");
    let tags = req.member.focus_tags.join("、");
    format!(
        "你正在扮演群聊里的「{}」（{}），关注点：{}。\n下面是最近的对话片段：\n{}\n\n新消息来自 [{}]：\n{}\n\n判断：你是否应该出声回应这条消息？只输出严格的 JSON：{{\"should_reply\": true/false, \"confidence\": 0.0-1.0, \"reason\": \"...\", \"suggested_delay_ms\": 0}}",
        req.member.name,
        personality,
        tags,
        history_excerpt,
        req.trigger_sender_name,
        truncate(&req.trigger_content, 600),
    )
}

pub const LLM_JUDGE_SYSTEM: &str = "你是一个判断助手，只输出 JSON。";
