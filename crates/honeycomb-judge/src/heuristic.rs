use crate::context::JudgeRequest;
use crate::types::{Judgment, TriggerSenderKind};

pub fn evaluate(req: &JudgeRequest) -> Judgment {
    let h = &req.group_judge.heuristic;
    if req
        .mentions
        .iter()
        .any(|m| m == &req.member.id || m == &req.member.name)
    {
        return Judgment {
            should_reply: true,
            confidence: h.mention_confidence,
            reason: Some("被 @ 提及".into()),
            suggested_delay_ms: h.mention_delay_ms,
        };
    }
    match req.trigger_sender {
        TriggerSenderKind::User => Judgment {
            should_reply: true,
            confidence: h.user_confidence,
            reason: Some("群聊用户消息（启发式 judge）".into()),
            suggested_delay_ms: h.user_delay_ms,
        },
        TriggerSenderKind::Friend => Judgment {
            should_reply: true,
            confidence: h.friend_confidence,
            reason: Some("其他成员发言，可接话".into()),
            suggested_delay_ms: h.friend_delay_ms,
        },
        TriggerSenderKind::System => Judgment::default(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::context::JudgeMember;
    use crate::types::GroupJudgeSettings;

    #[test]
    fn user_message_gets_reply() {
        let req = JudgeRequest {
            group_judge: GroupJudgeSettings::default(),
            member: JudgeMember {
                id: "a".into(),
                name: "码农".into(),
                personality: None,
                focus_tags: vec![],
                judge_provider_ref: None,
            },
            trigger_sender: TriggerSenderKind::User,
            trigger_sender_id: "u".into(),
            trigger_sender_name: "你".into(),
            trigger_content: "topic".into(),
            mentions: vec![],
            history: vec![],
            extra_group_prompt: None,
        };
        let j = evaluate(&req);
        assert!(j.should_reply);
        assert!(j.confidence >= 0.55);
    }
}
