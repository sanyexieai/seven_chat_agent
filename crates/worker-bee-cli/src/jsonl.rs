use serde::Serialize;
use uuid::Uuid;

#[derive(Serialize)]
struct ItemCompleted<'a> {
    #[serde(rename = "type")]
    ty: &'static str,
    item: AgentMessageItem<'a>,
}

#[derive(Serialize)]
struct AgentMessageItem<'a> {
    id: String,
    #[serde(rename = "type")]
    ty: &'static str,
    text: &'a str,
}

/// 输出与 honeycomb `CodexExecJsonlParser` 兼容的一行 JSONL。
pub fn emit_agent_message(text: &str) -> String {
    let line = ItemCompleted {
        ty: "item.completed",
        item: AgentMessageItem {
            id: format!("item_{}", Uuid::new_v4().simple()),
            ty: "agent_message",
            text,
        },
    };
    serde_json::to_string(&line).expect("jsonl serialize")
}
