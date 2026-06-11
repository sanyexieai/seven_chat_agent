//! 群聊上下文：把消息送达状态写进 Agent / Judge 可见的文本，避免忽略失败发言。

use crate::domain::{Message, MessageStatus, SenderKind};

/// 单条消息正文（含失败/空内容等状态说明）。
pub fn format_message_content_for_context(m: &Message) -> String {
    let body = m.content.trim();
    match m.status {
        MessageStatus::Failed => {
            if body.is_empty() {
                "（消息发送失败，无有效内容）".into()
            } else {
                format!("（发送失败）{body}")
            }
        }
        MessageStatus::Streaming => {
            if body.is_empty() {
                "（仍在输出中…）".into()
            } else {
                format!("（仍在输出中…）{body}")
            }
        }
        MessageStatus::WaitingHuman => {
            if body.is_empty() {
                "（等待人工确认）".into()
            } else {
                format!("（等待人工确认）{body}")
            }
        }
        _ if body.is_empty() => "（空消息）".into(),
        _ => m.content.clone(),
    }
}

/// 群成员发言行（用于 LLM 历史与 Judge）。
pub fn format_peer_message_for_context(m: &Message) -> String {
    let name = match m.status {
        MessageStatus::Failed => format!("{}·发送失败", m.sender_name),
        _ => m.sender_name.clone(),
    };
    format!("[{name}]: {}", format_message_content_for_context(m))
}

/// 近期群聊摘录（接话 prompt 用，要求成员先阅读再回应）。
pub fn summarize_recent_dialogue_excerpt(
    history: &[Message],
    self_friend_id: &str,
    max_messages: usize,
) -> String {
    let lines: Vec<String> = history
        .iter()
        .rev()
        .filter(|m| {
            m.sender_kind != SenderKind::System
                && !(m.sender_kind == SenderKind::Friend && m.sender_id == self_friend_id)
        })
        .take(max_messages)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .map(|m| {
            let who = match m.sender_kind {
                SenderKind::User => "用户".to_string(),
                SenderKind::Friend => m.sender_name.clone(),
                SenderKind::System => "系统".into(),
            };
            format!("- {who}：{}", format_message_content_for_context(m))
        })
        .collect();
    if lines.is_empty() {
        "（暂无近期他人发言）".into()
    } else {
        lines.join("\n")
    }
}

/// 本回合其他 Agent 的失败摘要，注入接话 prompt。
pub fn summarize_same_turn_peer_failures(
    history: &[Message],
    turn_id: &str,
    self_friend_id: &str,
) -> Option<String> {
    let failures: Vec<String> = history
        .iter()
        .filter(|m| {
            m.turn_id == turn_id
                && m.status == MessageStatus::Failed
                && m.sender_kind == SenderKind::Friend
                && m.sender_id != self_friend_id
        })
        .map(|m| {
            format!(
                "- {}：{}",
                m.sender_name,
                format_message_content_for_context(m)
            )
        })
        .collect();
    if failures.is_empty() {
        return None;
    }
    Some(format!(
        "【本回合其他成员发言失败】\n{}\n\
         请先阅读上述失败信息：不要当作对方已成功表达观点；\
         若你能说明原因、接手或提醒用户检查配置，请明确写出。",
        failures.join("\n")
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::MessageStatus;
    use chrono::Utc;

    fn msg(status: MessageStatus, content: &str) -> Message {
        Message {
            id: "m".into(),
            conversation_id: "c".into(),
            turn_id: "t1".into(),
            parent_id: None,
            sender_kind: SenderKind::Friend,
            sender_id: "a".into(),
            sender_name: "甲".into(),
            content: content.into(),
            content_blocks: None,
            mentions: vec![],
            status,
            seen_by: vec![],
            model_used: None,
            tokens_in: None,
            tokens_out: None,
            on_behalf_of_user: false,
            workspace_id: None,
            attachments: vec![],
            created_at: Utc::now(),
        }
    }

    #[test]
    fn recent_dialogue_lists_peers_and_user() {
        let mut user = msg(MessageStatus::Done, "大家看看登录模块");
        user.sender_kind = SenderKind::User;
        user.sender_name = "你".into();
        let excerpt = summarize_recent_dialogue_excerpt(&[user], "a", 8);
        assert!(excerpt.contains("用户"));
        assert!(excerpt.contains("登录模块"));
    }

    #[test]
    fn failed_message_marked_in_peer_line() {
        let line = format_peer_message_for_context(&msg(
            MessageStatus::Failed,
            "(error: api key)",
        ));
        assert!(line.contains("发送失败"));
        assert!(line.contains("（发送失败）"));
    }

    #[test]
    fn same_turn_failure_summary_excludes_self() {
        let mut b = msg(MessageStatus::Failed, "(error: x)");
        b.sender_id = "b".into();
        b.sender_name = "乙".into();
        let note = summarize_same_turn_peer_failures(&[b], "t1", "a").expect("note");
        assert!(note.contains("乙"));
    }
}
