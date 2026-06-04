use crate::context::JudgeRequest;
use crate::redundancy::{
    focus_tags_relevant, has_open_question, member_recently_redundant, trigger_echoes_recent,
};
use crate::types::{JudgeSource, Judgment, TriggerSenderKind};

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
            source: Some(JudgeSource::Heuristic),
        };
    }

    let recent: Vec<String> = req
        .history
        .iter()
        .rev()
        .take(12)
        .map(|line| line.content.clone())
        .collect();

    if trigger_echoes_recent(&req.trigger_content, &recent, 0.72) {
        return Judgment {
            should_reply: false,
            confidence: 0.12,
            reason: Some("触发消息与近期内容高度重复，避免空转接龙".into()),
            suggested_delay_ms: 0,
            source: Some(JudgeSource::Heuristic),
        };
    }

    if member_recently_redundant(&req.member.name, &req.history, &req.trigger_content, 0.68) {
        return Judgment {
            should_reply: false,
            confidence: 0.15,
            reason: Some("你近期已表达类似观点，无新进展则不接话".into()),
            suggested_delay_ms: 0,
            source: Some(JudgeSource::Heuristic),
        };
    }

    match req.trigger_sender {
        TriggerSenderKind::User => {
            let domain = focus_tags_relevant(&req.member.focus_tags, &req.trigger_content);
            let question = has_open_question(&req.trigger_content);
            if domain || question {
                Judgment {
                    should_reply: true,
                    confidence: h.user_confidence,
                    reason: Some(if domain {
                        "用户消息与专长相关，可补充新观点".into()
                    } else {
                        "用户提出疑问，可回应".into()
                    }),
                    suggested_delay_ms: h.user_delay_ms,
                    source: Some(JudgeSource::Heuristic),
                }
            } else {
                Judgment {
                    should_reply: true,
                    confidence: h.user_confidence * 0.85,
                    reason: Some("用户消息（启发式；须有不同于他人的新内容）".into()),
                    suggested_delay_ms: h.user_delay_ms,
                    source: Some(JudgeSource::Heuristic),
                }
            }
        }
        TriggerSenderKind::Friend => {
            let question = has_open_question(&req.trigger_content);
            let domain = focus_tags_relevant(&req.member.focus_tags, &req.trigger_content);
            if question || domain {
                Judgment {
                    should_reply: true,
                    confidence: if question {
                        h.friend_confidence
                    } else {
                        h.friend_confidence * 0.9
                    },
                    reason: Some(if question {
                        "有未决疑问，可接话补充".into()
                    } else {
                        "专长相关，可提供新进展".into()
                    }),
                    suggested_delay_ms: h.friend_delay_ms,
                    source: Some(JudgeSource::Heuristic),
                }
            } else {
                Judgment {
                    should_reply: false,
                    confidence: 0.22,
                    reason: Some("无新疑问或专长相关点，避免重复接话".into()),
                    suggested_delay_ms: 0,
                    source: Some(JudgeSource::Heuristic),
                }
            }
        }
        TriggerSenderKind::System => Judgment::default(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::context::JudgeMember;
    use crate::types::GroupJudgeSettings;

    fn base_req(trigger: TriggerSenderKind, content: &str) -> JudgeRequest {
        JudgeRequest {
            group_judge: GroupJudgeSettings::default(),
            member: JudgeMember {
                id: "a".into(),
                name: "码农".into(),
                personality: None,
                focus_tags: vec!["Rust".into()],
                judge_provider_ref: None,
            },
            trigger_sender: trigger,
            trigger_sender_id: "u".into(),
            trigger_sender_name: "你".into(),
            trigger_content: content.into(),
            mentions: vec![],
            history: vec![],
            extra_group_prompt: None,
        }
    }

    #[test]
    fn user_message_gets_reply() {
        let j = evaluate(&base_req(TriggerSenderKind::User, "Rust 异步怎么设计？"));
        assert!(j.should_reply);
    }

    #[test]
    fn friend_generic_statement_skipped() {
        let j = evaluate(&base_req(
            TriggerSenderKind::Friend,
            "我觉得可以再看看文档。",
        ));
        assert!(!j.should_reply);
    }

    #[test]
    fn friend_question_can_reply() {
        let j = evaluate(&base_req(
            TriggerSenderKind::Friend,
            "仓库地址是什么？",
        ));
        assert!(j.should_reply);
    }
}
