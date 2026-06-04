use crate::context::JudgeRequest;
use crate::types::TriggerSenderKind;

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
        .take(8)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .map(|m| format!("[{}]: {}", m.sender_name, truncate(&m.content, 160)))
        .collect::<Vec<_>>()
        .join("\n");
    let personality = req.member.personality.as_deref().unwrap_or("");
    let tags = req.member.focus_tags.join("、");
    let trigger_kind = match req.trigger_sender {
        TriggerSenderKind::User => "用户",
        TriggerSenderKind::Friend => "其他成员（Agent/真人）",
        TriggerSenderKind::System => "系统",
    };
    format!(
        "你正在扮演群聊里的「{}」（{}），关注点：{}。\n下面是最近的对话片段：\n{}\n\n新消息来自 [{trigger_kind}]「{}」：\n{}\n\n\
        **接话原则**（should_reply=true 须满足至少一条）：\n\
        1. 你能提供与近期消息**不同**的新信息、新进展或可执行结论\n\
        2. 存在需要**该成员**回答的、尚未解决的**具体**疑问\n\
        3. 被 @ 或消息明确点名该成员\n\n\
        **不应接话**（should_reply=false）：\n\
        - 他人已问过/说过同样意思，你只是重复或换说法附和\n\
        - 没有新进展，仅为刷存在感\n\
        - 触发消息来自其他 Agent 且你无新的专业补充或新疑问\n\n\
        若触发来自其他成员，门槛更高：除非有新观点或新疑问，否则 should_reply=false。\n\n\
        只输出严格的 JSON：{{\"should_reply\": true/false, \"confidence\": 0.0-1.0, \"reason\": \"一句话说明为何接/不接\", \"suggested_delay_ms\": 0}}",
        req.member.name,
        personality,
        tags,
        history_excerpt,
        req.trigger_sender_name,
        truncate(&req.trigger_content, 600),
    )
}

pub const LLM_JUDGE_SYSTEM: &str =
    "你是群聊接话判断助手。只在成员确有新进展、新观点或未决疑问时才应接话；禁止同一问题在多个 agent 间重复空转。只输出 JSON。";
