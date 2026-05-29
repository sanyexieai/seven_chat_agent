use super::{BusEvent, MessageDispatcher};
use crate::agent::ChatContext;
use crate::domain::{
    BackendKind, Conversation, Friend, GroupSettings, Message, MessageStatus, SenderKind,
};
use crate::group_validate::validate_group_task_flow_readiness;
use crate::store::message::NewMessage;
use seven_chat_agent_judge::format_peer_vote_tally;
use crate::Result;

impl MessageDispatcher {
    /// 任务流：任命/竞选 → 互投 → 选举 → 计划 → 评议 → 执行。
    pub(super) async fn run_task_flow(
        &self,
        conv: &Conversation,
        user_msg: &Message,
        turn_id: &str,
        settings: &GroupSettings,
        members: &[Friend],
    ) -> Result<bool> {
        if !settings.task_flow.enabled {
            return Ok(false);
        }

        let member_ids: Vec<String> = members.iter().map(|m| m.id.clone()).collect();
        let readiness = validate_group_task_flow_readiness(
            &self.store,
            &self.judge.provider_registry(),
            settings,
            &member_ids,
        )
        .await?;
        if !readiness.ready {
            tracing::warn!(
                turn_id = %turn_id,
                errors = ?readiness.errors,
                "task_flow: group not ready, skipping"
            );
            self.emit_task_flow_config_notice(conv, &readiness.errors)
                .await?;
            return Ok(true);
        }

        let agents: Vec<Friend> = members
            .iter()
            .filter(|m| m.backend_kind != BackendKind::Human)
            .cloned()
            .collect();
        if agents.is_empty() {
            tracing::warn!(turn_id = %turn_id, "task_flow: no agent members, skip");
            return Ok(false);
        }

        let tf = &settings.task_flow;
        let mut pitches: Vec<(String, String, String)> = Vec::new();
        let elected = if tf.appoint_by_mention_enabled {
            if let Some((id, name, reason)) = resolve_appointed_leader(user_msg, &agents) {
                self.emit(BusEvent::TaskFlowPhase {
                    conversation_id: conv.id.clone(),
                    turn_id: turn_id.to_string(),
                    phase: "appoint".into(),
                    detail: Some(format!("用户指定 {} 为负责人", name)),
                });
                tracing::info!(turn_id = %turn_id, leader = %name, "task_flow: appointed by mention");
                Ok((id, name, reason, 1.0, Vec::new()))
            } else {
                self.run_campaign_and_elect(
                    conv, user_msg, turn_id, settings, &agents, tf, &mut pitches,
                )
                .await
            }
        } else {
            self.run_campaign_and_elect(
                conv, user_msg, turn_id, settings, &agents, tf, &mut pitches,
            )
            .await
        };
        let (leader_id, leader_name, elect_reason, confidence, peer_vote_pairs) = match elected {
            Ok(v) => v,
            Err(e) => {
                tracing::warn!(turn_id = %turn_id, err = %e, "task_flow: campaign/elect aborted");
                return Ok(false);
            }
        };

        let election_ok = elect_reason.contains("用户 @ 指定")
            || elect_reason.contains("用户消息包含")
            || (confidence >= 0.55
                && !elect_reason.contains("失败")
                && !elect_reason.contains("兜底")
                && !elect_reason.contains("互投均未")
                && !elect_reason.contains("API 失败"));
        let peer_votes_summary = if peer_vote_pairs.is_empty() {
            Some("互投：均未成功（请检查群 Judge 的 Provider/模型，如 deepseek 需 deepseek-v4-flash）".into())
        } else {
            Some(format_peer_vote_tally(
                &peer_vote_pairs,
                &agents
                    .iter()
                    .map(|m| (m.id.clone(), m.name.clone()))
                    .collect::<Vec<_>>(),
            ))
        };
        tracing::info!(
            turn_id = %turn_id,
            leader_id = %leader_id,
            leader = %leader_name,
            confidence = confidence,
            election_ok = election_ok,
            reason = %elect_reason,
            peer_votes = ?peer_votes_summary,
            campaign_pitches = pitches.len(),
            "task_flow: leader_elected"
        );
        self.emit(BusEvent::LeaderElected {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.to_string(),
            friend_id: leader_id.clone(),
            friend_name: leader_name.clone(),
            reason: elect_reason.clone(),
            confidence,
            election_ok,
            peer_votes_summary,
            pitches: pitches
                .iter()
                .map(|(id, name, _)| (id.clone(), name.clone()))
                .collect(),
        });

        let leader = agents
            .iter()
            .find(|m| m.id == leader_id)
            .cloned()
            .or_else(|| agents.first().cloned())
            .expect("leader exists");

        let campaign_summary = if pitches.is_empty() {
            String::new()
        } else {
            pitches
                .iter()
                .map(|(_, name, content)| format!("【{name} 竞选】\n{content}"))
                .collect::<Vec<_>>()
                .join("\n\n")
        };

        let mut plan_text = String::new();
        if tf.plan_enabled {
            plan_text = self
                .run_plan_phase(
                    conv,
                    user_msg,
                    turn_id,
                    settings,
                    &agents,
                    &leader,
                    &elect_reason,
                    &campaign_summary,
                    tf.plan_review_enabled,
                )
                .await?;
        }

        self.emit(BusEvent::TaskFlowPhase {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.to_string(),
            phase: "execute".into(),
            detail: Some(format!("负责人 {} 按计划在执行", leader.name)),
        });

        let agent = self.agents.get(&leader.id).await?;
        let history = self.store.recent_messages(&conv.id, 60).await?;
        let ctx = ChatContext {
            conversation_id: conv.id.clone(),
            group_id: Some(conv.target_id.clone()),
            group_settings: Some(settings.clone()),
            history,
            self_friend: leader.clone(),
            peers: agents.iter().filter(|m| m.id != leader.id).cloned().collect(),
        };
        let plan_block = if plan_text.is_empty() {
            "（无单独计划稿，请边计划边执行）".to_string()
        } else {
            format!("已发布计划：\n{plan_text}")
        };
        let prompt = format!(
            "你是本轮任务负责人「{}」。选举/任命理由：{}\n\n用户任务：\n{}\n\n竞选摘要：\n{}\n\n{plan_block}\n\n\
            请进入执行阶段：按已定计划使用工具完成任务（查代码、跑命令等），可多步；完成后给用户清晰总结。",
            leader.name, elect_reason, user_msg.content, campaign_summary, plan_block = plan_block
        );
        let _ = self
            .stream_one_reply(conv, user_msg, turn_id, &leader, agent, ctx, &prompt, 0)
            .await?;

        Ok(true)
    }

    async fn run_campaign_and_elect(
        &self,
        conv: &Conversation,
        user_msg: &Message,
        turn_id: &str,
        settings: &GroupSettings,
        agents: &[Friend],
        tf: &crate::domain::GroupTaskFlowSettings,
        pitches: &mut Vec<(String, String, String)>,
    ) -> Result<(String, String, String, f32, Vec<(String, String)>)> {
        let peer_names: Vec<String> = agents.iter().map(|m| m.name.clone()).collect();

        if tf.campaign_enabled {
            self.emit(BusEvent::TaskFlowPhase {
                conversation_id: conv.id.clone(),
                turn_id: turn_id.to_string(),
                phase: "campaign".into(),
                detail: Some("成员竞选负责人：陈述优势并争取认可".into()),
            });
            for friend in agents {
                let agent = self.agents.get(&friend.id).await?;
                let peers: Vec<Friend> = agents
                    .iter()
                    .filter(|m| m.id != friend.id)
                    .cloned()
                    .collect();
                let history = self.store.recent_messages(&conv.id, 40).await?;
                let ctx = ChatContext {
                    conversation_id: conv.id.clone(),
                    group_id: Some(conv.target_id.clone()),
                    group_settings: Some(settings.clone()),
                    history,
                    self_friend: friend.clone(),
                    peers,
                };
                let others = peer_names
                    .iter()
                    .filter(|n| *n != &friend.name)
                    .cloned()
                    .collect::<Vec<_>>()
                    .join("、");
                let prompt = format!(
                    "【竞选负责人】用户任务：\n{}\n\n其他 Agent：{}\n\n你是「{}」。请竞选本轮负责人：\n\
                    1. 你的优势与能交付什么\n2. 说服他人选你\n3. 若负责的 2–4 点执行思路\n\n\
                    仅竞选发言，不要执行工具/写代码。",
                    user_msg.content,
                    if others.is_empty() { "（无）".into() } else { others },
                    friend.name,
                );
                if let Some(msg) = self
                    .stream_one_reply(conv, user_msg, turn_id, friend, agent, ctx, &prompt, 0)
                    .await?
                {
                    pitches.push((friend.id.clone(), friend.name.clone(), msg.content));
                    self.emit(BusEvent::CampaignPitch {
                        conversation_id: conv.id.clone(),
                        turn_id: turn_id.to_string(),
                        friend_id: friend.id.clone(),
                        friend_name: friend.name.clone(),
                    });
                }
            }
        } else {
            for friend in agents {
                pitches.push((
                    friend.id.clone(),
                    friend.name.clone(),
                    format!("（跳过竞选）{} 参选。", friend.name),
                ));
            }
        }

        if pitches.is_empty() {
            return Err(crate::Error::Config("task_flow: no campaign pitches".into()));
        }

        let mut peer_vote_pairs: Vec<(String, String)> = Vec::new();
        if tf.peer_vote_enabled && agents.len() > 1 {
            self.emit(BusEvent::TaskFlowPhase {
                conversation_id: conv.id.clone(),
                turn_id: turn_id.to_string(),
                phase: "peer_vote".into(),
                detail: Some("成员阅读竞选稿并互投背书".into()),
            });
            for voter in agents {
                match self
                    .judge
                    .cast_peer_vote(
                        settings,
                        &voter.name,
                        &voter.id,
                        &user_msg.content,
                        pitches,
                    )
                    .await
                {
                    Ok((endorse_id, reason)) => {
                        let endorse_name = agents
                            .iter()
                            .find(|m| m.id == endorse_id)
                            .map(|m| m.name.clone())
                            .unwrap_or_else(|| endorse_id.clone());
                        peer_vote_pairs.push((voter.id.clone(), endorse_id.clone()));
                        tracing::info!(
                            turn_id = %turn_id,
                            voter = %voter.name,
                            endorse = %endorse_name,
                            reason = %reason,
                            "task_flow: peer_vote"
                        );
                        self.emit(BusEvent::PeerVote {
                            conversation_id: conv.id.clone(),
                            turn_id: turn_id.to_string(),
                            voter_id: voter.id.clone(),
                            voter_name: voter.name.clone(),
                            endorse_id,
                            endorse_name,
                            reason,
                        });
                    }
                    Err(e) => {
                        tracing::warn!(
                            voter = %voter.name,
                            err = %e,
                            "task_flow: peer vote failed"
                        );
                        self.emit(BusEvent::PeerVoteFailed {
                            conversation_id: conv.id.clone(),
                            turn_id: turn_id.to_string(),
                            voter_id: voter.id.clone(),
                            voter_name: voter.name.clone(),
                            error: e,
                        });
                    }
                }
            }
        }

        self.emit(BusEvent::TaskFlowPhase {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.to_string(),
            phase: "election".into(),
            detail: Some("综合互投与 LLM 选举负责人".into()),
        });

        let id_names: Vec<(String, String)> = agents
            .iter()
            .map(|m| (m.id.clone(), m.name.clone()))
            .collect();
        let tally_str = if peer_vote_pairs.is_empty() {
            None
        } else {
            Some(format_peer_vote_tally(&peer_vote_pairs, &id_names))
        };

        let candidate_ids: Vec<String> = agents.iter().map(|m| m.id.clone()).collect();
        let election = self
            .judge
            .elect_leader(
                settings,
                &user_msg.content,
                pitches,
                &candidate_ids,
                tally_str.as_deref(),
            )
            .await;

        Ok(match election {
            Ok((id, name, reason, conf)) => (id, name, reason, conf, peer_vote_pairs),
            Err(e) => {
                let err_short = if e.len() > 120 {
                    format!("{}…", &e[..120])
                } else {
                    e.clone()
                };
                if let Some((id, count)) = seven_chat_agent_judge::tally_peer_votes(&peer_vote_pairs).first()
                {
                    let name = id_names
                        .iter()
                        .find(|(i, _)| i == id)
                        .map(|(_, n)| n.clone())
                        .unwrap_or_else(|| id.clone());
                    (
                        id.clone(),
                        name,
                        format!("LLM 选举 API 失败（{err_short}），按互投最高票（{count} 票）"),
                        0.6,
                        peer_vote_pairs,
                    )
                } else if let Some((id, name, _)) = pitches.first() {
                    (
                        id.clone(),
                        name.clone(),
                        format!(
                            "LLM 选举与互投均未完成（{err_short}），按竞选发言顺序首位「{name}」兜底（非 LLM 选定）"
                        ),
                        0.5,
                        peer_vote_pairs,
                    )
                } else {
                    let f = &agents[0];
                    (
                        f.id.clone(),
                        f.name.clone(),
                        format!("选举失败（{err_short}），默认成员列表首位"),
                        0.5,
                        peer_vote_pairs,
                    )
                }
            }
        })
    }

    async fn run_plan_phase(
        &self,
        conv: &Conversation,
        user_msg: &Message,
        turn_id: &str,
        settings: &GroupSettings,
        agents: &[Friend],
        leader: &Friend,
        elect_reason: &str,
        campaign_summary: &str,
        plan_review_enabled: bool,
    ) -> Result<String> {
        self.emit(BusEvent::TaskFlowPhase {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.to_string(),
            phase: "plan".into(),
            detail: Some(format!("负责人 {} 制定计划", leader.name)),
        });

        let agent = self.agents.get(&leader.id).await?;
        let history = self.store.recent_messages(&conv.id, 60).await?;
        let ctx = ChatContext {
            conversation_id: conv.id.clone(),
            group_id: Some(conv.target_id.clone()),
            group_settings: Some(settings.clone()),
            history,
            self_friend: leader.clone(),
            peers: agents.iter().filter(|m| m.id != leader.id).cloned().collect(),
        };
        let plan_prompt = format!(
            "你是负责人「{}」。任命/选举理由：{}\n\n用户任务：\n{}\n\n竞选摘要：\n{}\n\n\
            请发布【执行计划】（本阶段不跑工具、不写代码）：\n\
            - 目标与成功标准\n- 步骤 1..N（谁做什么、产出物）\n- 风险与假设\n- 预计给用户的交付物形态",
            leader.name, elect_reason, user_msg.content, campaign_summary
        );
        let plan_msg = self
            .stream_one_reply(conv, user_msg, turn_id, leader, agent, ctx, &plan_prompt, 0)
            .await?;
        let plan_text = plan_msg
            .map(|m| m.content)
            .unwrap_or_else(|| "（计划未生成）".into());
        let excerpt: String = plan_text.chars().take(240).collect();
        self.emit(BusEvent::PlanPublished {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.to_string(),
            friend_id: leader.id.clone(),
            friend_name: leader.name.clone(),
            plan_excerpt: excerpt,
        });

        if plan_review_enabled && agents.len() > 1 {
            self.emit(BusEvent::TaskFlowPhase {
                conversation_id: conv.id.clone(),
                turn_id: turn_id.to_string(),
                phase: "plan_review".into(),
                detail: Some("成员对计划简短评议".into()),
            });
            for member in agents.iter().filter(|m| m.id != leader.id) {
                let agent = self.agents.get(&member.id).await?;
                let history = self.store.recent_messages(&conv.id, 60).await?;
                let ctx = ChatContext {
                    conversation_id: conv.id.clone(),
                    group_id: Some(conv.target_id.clone()),
                    group_settings: Some(settings.clone()),
                    history,
                    self_friend: member.clone(),
                    peers: vec![leader.clone()],
                };
                let prompt = format!(
                    "负责人「{}」发布了计划：\n{}\n\n你是「{}」。请用 1–3 句话评议：是否同意、需补充什么、是否愿意配合（不要抢执行权）。",
                    leader.name, plan_text, member.name
                );
                if let Some(msg) = self
                    .stream_one_reply(conv, user_msg, turn_id, member, agent, ctx, &prompt, 0)
                    .await?
                {
                    self.emit(BusEvent::PlanReview {
                        conversation_id: conv.id.clone(),
                        turn_id: turn_id.to_string(),
                        friend_id: member.id.clone(),
                        friend_name: member.name.clone(),
                        content: msg.content.chars().take(300).collect(),
                    });
                }
            }
        }

        Ok(plan_text)
    }

    async fn emit_task_flow_config_notice(
        &self,
        conv: &Conversation,
        errors: &[String],
    ) -> Result<()> {
        let content = format!(
            "⚠️ 群任务流配置不完整，本轮已跳过竞选/选举。请在群设置中修复并保存：\n{}",
            errors.join("\n")
        );
        let turn_id = uuid::Uuid::new_v4().to_string();
        let msg = self
            .store
            .insert_message(NewMessage {
                conversation_id: &conv.id,
                turn_id: &turn_id,
                parent_id: None,
                sender_kind: SenderKind::System,
                sender_id: "system",
                sender_name: "系统",
                content: &content,
                mentions: &[],
                status: MessageStatus::Done,
                on_behalf_of_user: false,
            })
            .await?;
        self.emit(BusEvent::MessageCreated { message: msg });
        Ok(())
    }
}

/// 从 mentions 或正文 @名字 解析指定负责人。
fn resolve_appointed_leader(
    user_msg: &Message,
    agents: &[Friend],
) -> Option<(String, String, String)> {
    for id in &user_msg.mentions {
        if let Some(f) = agents.iter().find(|m| m.id == *id || m.name == *id) {
            return Some((
                f.id.clone(),
                f.name.clone(),
                format!("用户 @ 指定 {} 为负责人", f.name),
            ));
        }
    }
    let content = &user_msg.content;
    for f in agents {
        let at_name = format!("@{}", f.name);
        if content.contains(&at_name) {
            return Some((
                f.id.clone(),
                f.name.clone(),
                format!("用户消息包含 {at_name}，指定为负责人"),
            ));
        }
    }
    None
}
