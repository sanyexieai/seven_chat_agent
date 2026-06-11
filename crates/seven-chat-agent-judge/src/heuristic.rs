use crate::context::JudgeRequest;
use crate::redundancy::{
    focus_tags_relevant, has_open_question, member_recently_redundant, trigger_echoes_recent,
};
use crate::types::{InitiativeLevel, JudgeSource, Judgment, TriggerSenderKind};

pub fn evaluate(req: &JudgeRequest) -> Judgment {
    apply_routing_hints(&base_evaluate(req), req)
}

fn member_mentioned(req: &JudgeRequest) -> bool {
    req.mentions
        .iter()
        .any(|m| m == &req.member.id || m == &req.member.name)
}

/// 按成员画像调整 judge 结果（调度层只读 routing_hints）。
pub fn apply_routing_hints(base: &Judgment, req: &JudgeRequest) -> Judgment {
    let Some(hints) = req.routing_hints.as_ref() else {
        return base.clone();
    };

    let mentioned = member_mentioned(req);

    if mentioned && hints.respond_to_mention {
        if base.should_reply {
            return base.clone();
        }
        let h = &req.group_judge.heuristic;
        return Judgment {
            should_reply: true,
            confidence: h.mention_confidence,
            reason: Some("被 @ 提及（成员画像：响应点名）".into()),
            suggested_delay_ms: h.mention_delay_ms,
            source: base.source.or(Some(JudgeSource::Heuristic)),
        };
    }

    match hints.initiative {
        InitiativeLevel::Passive if !mentioned => Judgment {
            should_reply: false,
            confidence: 0.08,
            reason: Some("被动型成员：未被点名或分配，不接话".into()),
            suggested_delay_ms: 0,
            source: Some(JudgeSource::Heuristic),
        },
        InitiativeLevel::Proactive
            if req.trigger_sender == TriggerSenderKind::User && base.should_reply =>
        {
            let h = &req.group_judge.heuristic;
            Judgment {
                confidence: base.confidence.max(h.user_confidence),
                ..base.clone()
            }
        }
        _ => base.clone(),
    }
}

fn base_evaluate(req: &JudgeRequest) -> Judgment {
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

    let consensus_peer_failure = req
        .group_context_excerpt
        .as_deref()
        .is_some_and(|s| s.contains("失败"));

    match req.trigger_sender {
        TriggerSenderKind::User => {
            let peer_failed_recently = consensus_peer_failure
                || req
                    .history
                    .iter()
                    .rev()
                    .take(6)
                    .any(|line| {
                        line.sender_name.contains("发送失败")
                            || line.content.contains("（发送失败）")
                    });
            if peer_failed_recently {
                return Judgment {
                    should_reply: true,
                    confidence: h.user_confidence,
                    reason: Some(
                        "近期有成员发言失败，请关注并必要时说明原因或接手，避免当作已成功接话"
                            .into(),
                    ),
                    suggested_delay_ms: h.user_delay_ms,
                    source: Some(JudgeSource::Heuristic),
                };
            }

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
            if consensus_peer_failure {
                return Judgment {
                    should_reply: true,
                    confidence: h.friend_confidence,
                    reason: Some(
                        "群共识记录有成员发言失败，请关注并必要时说明或接手".into(),
                    ),
                    suggested_delay_ms: h.friend_delay_ms,
                    source: Some(JudgeSource::Heuristic),
                };
            }
            let trigger_failed = req.trigger_content.contains("（发送失败）")
                || req.trigger_content.starts_with("(error:");
            if trigger_failed {
                return Judgment {
                    should_reply: true,
                    confidence: h.friend_confidence,
                    reason: Some(
                        "其他成员发言失败，可说明原因、接手或提醒用户检查配置".into(),
                    ),
                    suggested_delay_ms: h.friend_delay_ms,
                    source: Some(JudgeSource::Heuristic),
                };
            }

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
            routing_hints: None,
            persona_block: None,
            group_context_excerpt: None,
        }
    }

    #[test]
    fn group_consensus_failure_biases_user_trigger_to_reply() {
        let mut req = base_req(TriggerSenderKind::User, "继续吧");
        req.group_context_excerpt = Some("- 甲失败：发送失败".into());
        let j = evaluate(&req);
        assert!(j.should_reply);
        assert!(
            j.reason
                .as_deref()
                .is_some_and(|r| r.contains("失败") || r.contains("接手"))
        );
    }

    #[test]
    fn passive_skips_user_message_without_mention() {
        use crate::types::{InitiativeLevel, RoutingHints};
        let mut req = base_req(TriggerSenderKind::User, "大家下午好");
        req.routing_hints = Some(RoutingHints {
            initiative: InitiativeLevel::Passive,
            ..RoutingHints::default()
        });
        let j = evaluate(&req);
        assert!(!j.should_reply);
    }

    #[test]
    fn passive_replies_when_mentioned() {
        use crate::types::{InitiativeLevel, RoutingHints};
        let mut req = base_req(TriggerSenderKind::User, "@码农 看一下");
        req.mentions = vec!["码农".into()];
        req.routing_hints = Some(RoutingHints {
            initiative: InitiativeLevel::Passive,
            ..RoutingHints::default()
        });
        let j = evaluate(&req);
        assert!(j.should_reply);
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
