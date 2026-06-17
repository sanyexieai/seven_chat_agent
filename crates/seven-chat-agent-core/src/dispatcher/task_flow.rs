use super::delegate_continue::{enrich_delegation_mentions, parse_at_mention_assignees};
use super::{BusEvent, ExpertReplyMode, MessageDispatcher};
use crate::agent::ChatContext;
use crate::domain::{
    BackendKind, Conversation, Friend, GroupSettings, Message, MessageStatus, SenderKind,
};
use crate::group_validate::validate_group_task_flow_readiness;
use crate::profile::{
    build_member_roster_with_hints, member_recent_capability_hints, merge_task_assignments,
    pick_coordinator, resolve_effective_profile_with, self_nomination_candidates,
    EffectiveMemberProfile, MemberProfileOverlay, ProfileFrameworkCatalog,
};
use crate::store::message::NewMessage;
use std::collections::HashMap;
use seven_chat_agent_judge::format_peer_vote_tally;
use crate::Result;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum TaskFlowExecuteOutcome {
    Delivered,
    Stalled,
    Incomplete,
}

#[derive(Debug, Clone)]
pub(super) struct TaskFlowCheckpoint {
    pub outcome: TaskFlowExecuteOutcome,
    pub leader: Friend,
    pub plan_text: String,
    pub campaign_summary: String,
    pub elect_reason: String,
    pub agents: Vec<Friend>,
}

pub(super) struct TaskFlowRunResult {
    pub handled: bool,
    pub checkpoint: Option<TaskFlowCheckpoint>,
}

#[derive(Default, Clone)]
struct ExecuteLoopParams {
    autonomous_directive: Option<String>,
    stagnation_suppress_rounds: u32,
}

struct ResolvedLeader {
    leader_id: String,
    leader_name: String,
    elect_reason: String,
    confidence: f32,
    peer_vote_pairs: Vec<(String, String)>,
    pitches: Vec<(String, String, String)>,
    coordinator_assignees: Vec<(String, String)>,
    reused: bool,
}

impl MessageDispatcher {
    /// 任务流：任命/竞选 → 互投 → 选举 → 计划 → 评议 → 执行。
    pub(super) async fn run_task_flow(
        &self,
        conv: &Conversation,
        user_msg: &Message,
        turn_id: &str,
        settings: &GroupSettings,
        members: &[Friend],
    ) -> Result<TaskFlowRunResult> {
        if !settings.task_flow.enabled {
            return Ok(TaskFlowRunResult {
                handled: false,
                checkpoint: None,
            });
        }

        let member_ids: Vec<String> = members.iter().map(|m| m.id.clone()).collect();
        let readiness = validate_group_task_flow_readiness(
            &self.dispatch_store(),
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
            return Ok(TaskFlowRunResult {
                handled: true,
                checkpoint: None,
            });
        }

        let agents: Vec<Friend> = members
            .iter()
            .filter(|m| m.backend_kind != BackendKind::Human)
            .cloned()
            .collect();
        if agents.is_empty() {
            tracing::warn!(turn_id = %turn_id, "task_flow: no agent members, skip");
            return Ok(TaskFlowRunResult {
                handled: false,
                checkpoint: None,
            });
        }

        let tf = &settings.task_flow;
        let resolved = match self
            .resolve_task_flow_leader(conv, user_msg, turn_id, settings, &agents, tf)
            .await
        {
            Ok(v) => v,
            Err(e) => {
                tracing::warn!(turn_id = %turn_id, err = %e, "task_flow: leader resolve aborted");
                return Ok(TaskFlowRunResult {
                    handled: false,
                    checkpoint: None,
                });
            }
        };

        let leader_id = resolved.leader_id.clone();
        let leader_name = resolved.leader_name.clone();
        let elect_reason = resolved.elect_reason.clone();
        let confidence = resolved.confidence;
        let peer_vote_pairs = resolved.peer_vote_pairs;
        let pitches = resolved.pitches;

        let election_ok = resolved.reused
            || elect_reason.contains("用户 @ 指定")
            || elect_reason.contains("用户消息包含")
            || (confidence >= 0.55
                && !elect_reason.contains("失败")
                && !elect_reason.contains("兜底")
                && !elect_reason.contains("互投均未")
                && !elect_reason.contains("API 失败"));
        let peer_votes_summary = if peer_vote_pairs.is_empty() {
            if resolved.reused {
                None
            } else {
                Some("互投：均未成功（请检查群 Judge 的 Provider/模型，如 deepseek 需 deepseek-v4-flash）".into())
            }
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
            reused = resolved.reused,
            reason = %elect_reason,
            peer_votes = ?peer_votes_summary,
            campaign_pitches = pitches.len(),
            "task_flow: leader_resolved"
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
        let (merged_ids, merged_names) = merge_task_assignments(
            &leader_id,
            &leader_name,
            &resolved.coordinator_assignees,
            &agents,
        );
        self.emit(BusEvent::TaskAssignmentsMerged {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.to_string(),
            leader_id: leader_id.clone(),
            leader_name: leader_name.clone(),
            assignee_ids: merged_ids.clone(),
            assignee_names: merged_names.clone(),
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
        if resolved.reused && tf.skip_plan_when_reuse_leader {
            if let Some(ref excerpt) = tf.persisted_plan_excerpt {
                if !excerpt.trim().is_empty() {
                    plan_text = format!("（沿用本群已定计划）\n{excerpt}");
                }
            }
        } else if tf.plan_enabled {
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
                    settings.effective_plan_review_enabled(),
                )
                .await?;
        }

        let plan_excerpt: String = plan_text.chars().take(240).collect();
        if let Err(e) = self
            .dispatch_store()
            .persist_group_task_flow_leader(
                &conv.target_id,
                &leader_id,
                &elect_reason,
                if plan_excerpt.is_empty() {
                    None
                } else {
                    Some(plan_excerpt.as_str())
                },
            )
            .await
        {
            tracing::warn!(err = %e, group_id = %conv.target_id, "task_flow: persist leader failed");
        }

        self.emit(BusEvent::TaskFlowPhase {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.to_string(),
            phase: "execute".into(),
            detail: Some(format!("负责人 {} 按计划在执行", leader.name)),
        });

        let outcome = self
            .run_execute_until_delivered(
                conv,
                user_msg,
                turn_id,
                settings,
                &agents,
                &leader,
                &plan_text,
                &campaign_summary,
                &elect_reason,
                &merged_names,
                tf,
                ExecuteLoopParams::default(),
            )
            .await?;

        Ok(TaskFlowRunResult {
            handled: true,
            checkpoint: Some(TaskFlowCheckpoint {
                outcome,
                leader,
                plan_text,
                campaign_summary,
                elect_reason,
                agents,
            }),
        })
    }

    async fn resolve_task_flow_leader(
        &self,
        conv: &Conversation,
        user_msg: &Message,
        turn_id: &str,
        settings: &GroupSettings,
        agents: &[Friend],
        tf: &crate::domain::GroupTaskFlowSettings,
    ) -> Result<ResolvedLeader> {
        if tf.appoint_by_mention_enabled {
            if let Some((id, name, reason)) = resolve_appointed_leader(user_msg, agents) {
                self.emit(BusEvent::TaskFlowPhase {
                    conversation_id: conv.id.clone(),
                    turn_id: turn_id.to_string(),
                    phase: "appoint".into(),
                    detail: Some(format!("用户指定 {} 为负责人", name)),
                });
                tracing::info!(turn_id = %turn_id, leader = %name, "task_flow: appointed by mention");
                return Ok(ResolvedLeader {
                    leader_id: id,
                    leader_name: name,
                    elect_reason: reason,
                    confidence: 1.0,
                    peer_vote_pairs: Vec::new(),
                    pitches: Vec::new(),
                    coordinator_assignees: Vec::new(),
                    reused: false,
                });
            }
        }

        if tf.reuse_persisted_leader {
            if let Some(ref pid) = tf.persisted_leader_id {
                if let Some(f) = agents.iter().find(|m| m.id == *pid) {
                    let reason = tf
                        .persisted_leader_reason
                        .clone()
                        .unwrap_or_else(|| "本群已选定负责人".into());
                    let elect_reason =
                        format!("沿用负责人「{}」：{reason}（按职责继续，跳过竞选/选举/计划）", f.name);
                    self.emit(BusEvent::TaskFlowPhase {
                        conversation_id: conv.id.clone(),
                        turn_id: turn_id.to_string(),
                        phase: "reuse_leader".into(),
                        detail: Some(format!("沿用负责人 {}，按职责继续", f.name)),
                    });
                    tracing::info!(
                        turn_id = %turn_id,
                        leader = %f.name,
                        "task_flow: reuse persisted leader"
                    );
                    return Ok(ResolvedLeader {
                        leader_id: f.id.clone(),
                        leader_name: f.name.clone(),
                        elect_reason,
                        confidence: 1.0,
                        peer_vote_pairs: Vec::new(),
                        pitches: Vec::new(),
                        coordinator_assignees: Vec::new(),
                        reused: true,
                    });
                }
            }
        }

        let mut pitches: Vec<(String, String, String)> = Vec::new();
        let (leader_id, leader_name, elect_reason, confidence, peer_vote_pairs, coordinator_assignees) =
            self
                .run_campaign_and_elect(conv, user_msg, turn_id, settings, agents, tf, &mut pitches)
                .await?;
        Ok(ResolvedLeader {
            leader_id,
            leader_name,
            elect_reason,
            confidence,
            peer_vote_pairs,
            pitches,
            coordinator_assignees,
            reused: false,
        })
    }

    /// 代理人授权后恢复执行（衔接「继续推进、不用每轮确认」）。
    pub(super) async fn resume_task_flow_after_delegate(
        &self,
        conv: &Conversation,
        user_msg: &Message,
        turn_id: &str,
        settings: &GroupSettings,
        checkpoint: &TaskFlowCheckpoint,
        delegate_directive: &str,
    ) -> Result<TaskFlowExecuteOutcome> {
        let tf = &settings.task_flow;
        self.emit(BusEvent::TaskFlowPhase {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.to_string(),
            phase: "execute".into(),
            detail: Some("代理人授权：恢复任务执行".into()),
        });
        self.run_execute_until_delivered(
            conv,
            user_msg,
            turn_id,
            settings,
            &checkpoint.agents,
            &checkpoint.leader,
            &checkpoint.plan_text,
            &checkpoint.campaign_summary,
            &checkpoint.elect_reason,
            &[],
            tf,
            ExecuteLoopParams {
                autonomous_directive: Some(delegate_directive.to_string()),
                stagnation_suppress_rounds: tf.resume_stagnation_suppress_rounds,
            },
        )
        .await
    }

    /// 负责人执行/引导循环：直到明确交付，或由内置助理判定空转暂停。
    async fn run_execute_until_delivered(
        &self,
        conv: &Conversation,
        user_msg: &Message,
        turn_id: &str,
        settings: &GroupSettings,
        agents: &[Friend],
        leader: &Friend,
        plan_text: &str,
        campaign_summary: &str,
        elect_reason: &str,
        assigned_names: &[String],
        tf: &crate::domain::GroupTaskFlowSettings,
        mut loop_params: ExecuteLoopParams,
    ) -> Result<TaskFlowExecuteOutcome> {
        let plan_block = if plan_text.is_empty() {
            "（无单独计划稿，请边计划边执行）".to_string()
        } else {
            format!("已发布计划：\n{plan_text}")
        };
        let assignment_block = if assigned_names.is_empty() {
            String::new()
        } else {
            format!(
                "\n协调分工涉及：{}。执行时请 @ 需要配合的成员，仅被点名者会接话协作。\n",
                assigned_names.join("、")
            )
        };

        let group_public_baseline = self
            .fetch_group_public_baseline_opt(&conv.target_id, settings)
            .await;

        let agent = self.agents.get(&leader.id).await?;
        let mut last_reply: Option<Message> = None;
        let mut last_missing = String::from("尚未形成可验收的明确交付");
        let mut leader_replies: Vec<String> = Vec::new();
        let mut round_idx: u32 = 0;

        loop {
            let is_first = round_idx == 0;
            let trigger = if is_first {
                user_msg.clone()
            } else {
                last_reply
                    .clone()
                    .unwrap_or_else(|| user_msg.clone())
            };

            let prompt = if is_first {
                if let Some(ref directive) = loop_params.autonomous_directive {
                    format!(
                        "你是本轮任务负责人「{}」。用户任务：\n{}\n\n{plan_block}\n\n\
                        **用户代理人已代主人定调（无需等主人每轮确认）**：\n{directive}\n\n\
                        请立即按此协调成员（@ 需要配合的人）、推进执行并产出可验收进展；\
                        不要等待主人再次确认才行动。",
                        leader.name,
                        user_msg.content,
                        plan_block = plan_block,
                        directive = directive.trim()
                    )
                } else {
                    format!(
                        "你是本轮任务负责人「{}」。选举/任命理由：{}\n\n用户任务：\n{}\n\n竞选摘要：\n{}\n\n{plan_block}{assignment_block}\n\
                        请进入执行阶段：按已定计划使用工具完成任务（查代码、跑命令等），可多步。\n\
                        **重要**：只有形成对用户的「明确交付」（可验收的产出/结论/变更说明）才能结束；\
                        若信息不足或任务未完成，应继续推进或向用户/成员提出具体问题，不要空泛收尾。",
                        leader.name,
                        elect_reason,
                        user_msg.content,
                        campaign_summary,
                        plan_block = plan_block,
                        assignment_block = assignment_block
                    )
                }
            } else {
                let prev = last_reply
                    .as_ref()
                    .map(|m| m.content.as_str())
                    .unwrap_or("");
                format!(
                    "你是本轮任务负责人「{}」。用户任务：\n{}\n\n{plan_block}\n\n\
                    你上一轮回复：\n{prev}\n\n\
                    **验收判定**：尚未形成明确交付。缺口：{last_missing}\n\n\
                    请继续引导讨论或推进执行（本阶段可多轮）：\n\
                    - 信息不足 → 向用户或群成员提出具体、可回答的问题\n\
                    - 可部分执行 → 说明当前进度、已完成部分与下一步\n\
                    - 接近完成 → 给出清晰交付摘要与验收标准\n\
                    不要假装已完成；直到用户能明确知道「得到了什么」再收尾。",
                    leader.name,
                    user_msg.content,
                    plan_block = plan_block,
                    prev = prev,
                    last_missing = last_missing
                )
            };

            if !is_first {
                self.emit(BusEvent::TaskFlowPhase {
                    conversation_id: conv.id.clone(),
                    turn_id: turn_id.to_string(),
                    phase: "guide".into(),
                    detail: Some(format!(
                        "第 {} 轮引导（{}）",
                        round_idx + 1,
                        last_missing
                    )),
                });
            }

            let history = self.dispatch_store().recent_messages(&conv.id, 60).await?;
            let ctx = ChatContext {
                conversation_id: conv.id.clone(),
                group_id: Some(conv.target_id.clone()),
                group_settings: Some(settings.clone()),
                history,
                self_friend: leader.clone(),
                peers: agents.iter().filter(|m| m.id != leader.id).cloned().collect(),
                user_attachments: user_msg.attachments.clone(),
                member_group_local_path: None,
                group_public_baseline: group_public_baseline.clone(),
            };

            let reply = self
                .stream_one_reply(
                    conv,
                    &trigger,
                    turn_id,
                    leader,
                    agent.clone(),
                    ctx,
                    &prompt,
                    0,
                )
                .await?;

            let Some(msg) = reply else {
                tracing::warn!(turn_id = %turn_id, round = round_idx, "task_flow: leader reply empty");
                return Ok(TaskFlowExecuteOutcome::Incomplete);
            };
            last_reply = Some(msg.clone());
            leader_replies.push(msg.content.clone());
            round_idx += 1;

            if agents.len() > 1 {
                if let Some(group) = self.dispatch_store().get_group(&conv.target_id).await? {
                    let mut peer_trigger = msg.clone();
                    peer_trigger.mentions = enrich_delegation_mentions(
                        &peer_trigger.content,
                        agents,
                        Some(&leader.id),
                    );
                    let peer_replies = self
                        .dispatch_expert_round(
                            conv,
                            &group,
                            settings,
                            &peer_trigger,
                            turn_id,
                            ExpertReplyMode::TaskFlowExecute,
                        )
                        .await?;
                    if !peer_replies.is_empty() {
                        tracing::info!(
                            turn_id = %turn_id,
                            round = round_idx,
                            peers = peer_replies.len(),
                            "task_flow: peer_collaboration_round"
                        );
                    }
                }
            }

            if !tf.require_clear_delivery {
                return Ok(TaskFlowExecuteOutcome::Delivered);
            }

            let check = self
                .judge
                .check_task_delivery(
                    settings,
                    &user_msg.content,
                    plan_text,
                    &leader.name,
                    &msg.content,
                )
                .await;

            tracing::info!(
                turn_id = %turn_id,
                round = round_idx,
                delivered = check.delivered,
                confidence = ?check.confidence,
                reason = ?check.reason,
                "task_flow: delivery_check"
            );

            let conf = check.confidence.unwrap_or(if check.delivered { 0.7 } else { 0.3 });
            if check.delivered && conf >= 0.5 {
                self.emit(BusEvent::TaskFlowPhase {
                    conversation_id: conv.id.clone(),
                    turn_id: turn_id.to_string(),
                    phase: "delivered".into(),
                    detail: check
                        .reason
                        .or_else(|| Some("已形成明确交付，本轮结束".into())),
                });
                return Ok(TaskFlowExecuteOutcome::Delivered);
            }

            last_missing = check
                .missing
                .filter(|s| !s.trim().is_empty())
                .or(check.reason.clone())
                .unwrap_or_else(|| "需继续推进任务或向用户澄清".into());

            let skip_stagnation = loop_params.stagnation_suppress_rounds > 0;
            if skip_stagnation {
                loop_params.stagnation_suppress_rounds -= 1;
            }
            let stagnation = self
                .judge
                .check_guidance_stagnation(
                    settings,
                    &user_msg.content,
                    plan_text,
                    &leader.name,
                    &leader_replies,
                    &last_missing,
                    loop_params.autonomous_directive.as_deref(),
                    skip_stagnation,
                )
                .await;

            tracing::info!(
                turn_id = %turn_id,
                round = round_idx,
                should_stop = stagnation.should_stop,
                confidence = ?stagnation.confidence,
                reason = ?stagnation.reason,
                "task_flow: assistant_stagnation_check"
            );

            let stall_conf = stagnation
                .confidence
                .unwrap_or(if stagnation.should_stop { 0.65 } else { 0.35 });
            if stagnation.should_stop && stall_conf >= 0.5 {
                let reason = stagnation
                    .reason
                    .unwrap_or_else(|| "助理判定引导陷入空转".into());
                let suggestion = stagnation
                    .suggestion
                    .unwrap_or_else(|| "请补充信息或调整任务后再 @ 负责人".into());
                self.emit(BusEvent::TaskFlowPhase {
                    conversation_id: conv.id.clone(),
                    turn_id: turn_id.to_string(),
                    phase: "stalled".into(),
                    detail: Some(format!("助理暂停引导：{reason}")),
                });
                self.emit_assistant_loop_guard_notice(conv, &reason, &suggestion)
                    .await?;
                return Ok(TaskFlowExecuteOutcome::Stalled);
            }
        }
    }

    async fn emit_assistant_loop_guard_notice(
        &self,
        conv: &Conversation,
        reason: &str,
        suggestion: &str,
    ) -> Result<()> {
        let content = format!(
            "⏸️ **助理监测**：引导循环已暂停。\n\n原因：{reason}\n\n建议：{suggestion}\n\n\
            （任务尚未确认明确交付；你补充信息或调整需求后，可再次 @ 负责人继续。）"
        );
        let turn_id = uuid::Uuid::new_v4().to_string();
        let msg = self
            .dispatch_store()
            .insert_message(NewMessage {
                conversation_id: &conv.id,
                turn_id: &turn_id,
                parent_id: None,
                sender_kind: SenderKind::System,
                sender_id: "system",
                sender_name: "助理",
                content: &content,
                mentions: &[],
                status: MessageStatus::Done,
                on_behalf_of_user: false,
                workspace_id: None,
                attachments: &[],
            })
            .await?;
        self.emit(BusEvent::MessageCreated { message: msg });
        Ok(())
    }

    async fn member_profile_overlays(&self, group_id: &str) -> Result<HashMap<String, MemberProfileOverlay>> {
        let configs = self.dispatch_store().list_group_member_configs(group_id).await?;
        Ok(configs
            .into_iter()
            .filter_map(|c| c.profile_overlay.map(|o| (c.friend_id, o)))
            .collect())
    }

    fn effective_profile_for(
        friend: &Friend,
        overlays: &HashMap<String, MemberProfileOverlay>,
        catalogs: &[ProfileFrameworkCatalog],
    ) -> EffectiveMemberProfile {
        resolve_effective_profile_with(
            friend,
            friend.profile.as_ref(),
            overlays.get(&friend.id),
            catalogs,
        )
    }

    async fn run_coordinator_plan(
        &self,
        conv: &Conversation,
        user_msg: &Message,
        turn_id: &str,
        settings: &GroupSettings,
        agents: &[Friend],
        coordinator: &Friend,
        overlays: &HashMap<String, MemberProfileOverlay>,
        catalogs: &[ProfileFrameworkCatalog],
    ) -> Result<Vec<(String, String)>> {
        let roster_pairs: Vec<_> = agents
            .iter()
            .map(|f| (f, Self::effective_profile_for(f, overlays, catalogs)))
            .collect();
        let roster_refs: Vec<(&Friend, EffectiveMemberProfile)> = roster_pairs
            .iter()
            .map(|(f, eff)| (*f, eff.clone()))
            .collect();
        let capability_hints = if let Ok(Some(aid)) =
            self.dispatch_store().builtin_assistant_id().await
        {
            member_recent_capability_hints(
                &self.dispatch_store(),
                &aid,
                &conv.target_id,
                agents,
            )
            .await
            .unwrap_or_default()
        } else {
            HashMap::new()
        };
        let roster = build_member_roster_with_hints(&roster_refs, &capability_hints);
        let group_public_baseline = self
            .fetch_group_public_baseline_opt(&conv.target_id, settings)
            .await;
        self.emit(BusEvent::TaskFlowPhase {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.to_string(),
            phase: "coordinator_plan".into(),
            detail: Some(format!("{} 协调分工", coordinator.name)),
        });
        let agent = self.agents.get(&coordinator.id).await?;
        let peers: Vec<Friend> = agents
            .iter()
            .filter(|m| m.id != coordinator.id)
            .cloned()
            .collect();
        let history = self.dispatch_store().recent_messages(&conv.id, 40).await?;
        let ctx = ChatContext {
            conversation_id: conv.id.clone(),
            group_id: Some(conv.target_id.clone()),
            group_settings: Some(settings.clone()),
            history,
            self_friend: coordinator.clone(),
            peers,
            user_attachments: user_msg.attachments.clone(),
            member_group_local_path: None,
            group_public_baseline: group_public_baseline.clone(),
        };
        let eff = Self::effective_profile_for(coordinator, overlays, catalogs);
        let persona = if eff.prompt_persona_block.is_empty() {
            String::new()
        } else {
            format!("\n{}\n", eff.prompt_persona_block)
        };
        let consensus_block = group_public_baseline
            .as_ref()
            .filter(|b| !b.trim().is_empty())
            .map(|b| format!("\n{b}\n"))
            .unwrap_or_default();
        let capability_excerpt = if let Ok(Some(aid)) =
            self.dispatch_store().builtin_assistant_id().await
        {
            crate::profile::format_group_capability_excerpt(
                &self.dispatch_store(),
                &aid,
                &conv.target_id,
                5,
            )
            .await
            .unwrap_or_default()
        } else {
            String::new()
        };
        let capability_block = if capability_excerpt.is_empty() {
            String::new()
        } else {
            format!("\n{capability_excerpt}\n")
        };
        let prompt = format!(
            "【协调分工】用户任务：\n{}\n\n本群成员能力：\n{}\n{consensus_block}{capability_block}{persona}\
             你是协调者「{}」。请：\n\
             1. 用 2–4 句话拆任务与优先级\n\
             2. 用 @成员名 明确分配（可多人）\n\
             3. 指定一位负责人主导交付\n\
             4. 若发现协作流程可改进，用 1 句话给出建议（仅建议，勿改仓库）\n\
             不要执行工具/写代码，仅规划与分工。",
            user_msg.content, roster, coordinator.name
        );
        let assignees = if let Some(msg) = self
            .stream_one_reply(conv, user_msg, turn_id, coordinator, agent, ctx, &prompt, 0)
            .await?
        {
            let assignees = parse_at_mention_assignees(&msg.content, agents);
            let excerpt = excerpt_text(&msg.content, 200);
            self.emit(BusEvent::CoordinatorPlan {
                conversation_id: conv.id.clone(),
                turn_id: turn_id.to_string(),
                planner_id: coordinator.id.clone(),
                planner_name: coordinator.name.clone(),
                assignee_ids: assignees.iter().map(|(id, _)| id.clone()).collect(),
                assignee_names: assignees.iter().map(|(_, n)| n.clone()).collect(),
                plan_excerpt: excerpt,
            });
            if let Ok(Some(aid)) = self.dispatch_store().builtin_assistant_id().await {
                if crate::profile::merge_coordinator_plan_into_group_public(
                    &self.dispatch_store(),
                    settings,
                    &aid,
                    &conv.target_id,
                    &msg.content,
                    &assignees,
                )
                .await
                .unwrap_or(false)
                {
                    self.emit_group_public_bus_event(&conv.id, &conv.target_id, turn_id)
                        .await;
                }
            }
            assignees
        } else {
            Vec::new()
        };
        Ok(assignees)
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
    ) -> Result<(
        String,
        String,
        String,
        f32,
        Vec<(String, String)>,
        Vec<(String, String)>,
    )> {
        let overlays = self.member_profile_overlays(&conv.target_id).await?;
        let catalogs = self.dispatch_store().all_profile_frameworks().await?;
        let peer_names: Vec<String> = agents.iter().map(|m| m.name.clone()).collect();
        let mut coordinator_assignees: Vec<(String, String)> = Vec::new();

        if let Some(coordinator) = pick_coordinator(agents, &overlays, &catalogs) {
            match self
                .run_coordinator_plan(
                    conv,
                    user_msg,
                    turn_id,
                    settings,
                    agents,
                    coordinator,
                    &overlays,
                    &catalogs,
                )
                .await
            {
                Ok(assignees) => coordinator_assignees = assignees,
                Err(e) => {
                    tracing::warn!(turn_id = %turn_id, err = %e, "task_flow: coordinator_plan failed");
                }
            }
        }

        let self_nominees = self_nomination_candidates(agents, &overlays, &catalogs);
        let group_public_baseline = self
            .fetch_group_public_baseline_opt(&conv.target_id, settings)
            .await;

        if tf.campaign_enabled {
            self.emit(BusEvent::TaskFlowPhase {
                conversation_id: conv.id.clone(),
                turn_id: turn_id.to_string(),
                phase: "campaign".into(),
                detail: Some(format!(
                    "主动型成员自荐（{} 人，非全员竞选）",
                    self_nominees.len().max(1)
                )),
            });
            let nominees = if self_nominees.is_empty() {
                agents.iter().collect::<Vec<_>>()
            } else {
                self_nominees
            };
            for friend in nominees {
                let agent = self.agents.get(&friend.id).await?;
                let peers: Vec<Friend> = agents
                    .iter()
                    .filter(|m| m.id != friend.id)
                    .cloned()
                    .collect();
                let history = self.dispatch_store().recent_messages(&conv.id, 40).await?;
                let ctx = ChatContext {
                    conversation_id: conv.id.clone(),
                    group_id: Some(conv.target_id.clone()),
                    group_settings: Some(settings.clone()),
                    history,
                    self_friend: friend.clone(),
                    peers,
                    user_attachments: user_msg.attachments.clone(),
                    member_group_local_path: None,
                    group_public_baseline: group_public_baseline.clone(),
                };
                let others = peer_names
                    .iter()
                    .filter(|n| *n != &friend.name)
                    .cloned()
                    .collect::<Vec<_>>()
                    .join("、");
                let eff = Self::effective_profile_for(friend, &overlays, &catalogs);
                let persona = if eff.prompt_persona_block.is_empty() {
                    String::new()
                } else {
                    format!("\n{}\n", eff.prompt_persona_block)
                };
                let prompt = format!(
                    "【自荐负责人】用户任务：\n{}\n\n其他 Agent：{}\n{persona}你是「{}」。若任务与专长匹配，请自荐本轮负责人：\n\
                    1. 你的优势与能交付什么\n2. 说服他人选你\n3. 若负责的 2–4 点执行思路\n\n\
                    若不匹配可简短说明并放弃。不要执行工具/写代码。",
                    user_msg.content,
                    if others.is_empty() { "（无）".into() } else { others },
                    friend.name,
                );
                if let Some(msg) = self
                    .stream_one_reply(conv, user_msg, turn_id, friend, agent, ctx, &prompt, 0)
                    .await?
                {
                    let excerpt = excerpt_text(&msg.content, 160);
                    pitches.push((friend.id.clone(), friend.name.clone(), msg.content));
                    self.emit(BusEvent::CampaignPitch {
                        conversation_id: conv.id.clone(),
                        turn_id: turn_id.to_string(),
                        friend_id: friend.id.clone(),
                        friend_name: friend.name.clone(),
                        pitch_excerpt: Some(excerpt),
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
        if settings.effective_peer_vote_enabled() && agents.len() > 1 {
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
            Ok((id, name, reason, conf)) => (
                id,
                name,
                reason,
                conf,
                peer_vote_pairs,
                coordinator_assignees,
            ),
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
                        coordinator_assignees,
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
                        coordinator_assignees,
                    )
                } else {
                    let f = &agents[0];
                    (
                        f.id.clone(),
                        f.name.clone(),
                        format!("选举失败（{err_short}），默认成员列表首位"),
                        0.5,
                        peer_vote_pairs,
                        coordinator_assignees,
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

        let group_public_baseline = self
            .fetch_group_public_baseline_opt(&conv.target_id, settings)
            .await;
        let agent = self.agents.get(&leader.id).await?;
        let history = self.dispatch_store().recent_messages(&conv.id, 60).await?;
        let ctx = ChatContext {
            conversation_id: conv.id.clone(),
            group_id: Some(conv.target_id.clone()),
            group_settings: Some(settings.clone()),
            history,
            self_friend: leader.clone(),
            peers: agents.iter().filter(|m| m.id != leader.id).cloned().collect(),
            user_attachments: user_msg.attachments.clone(),
            member_group_local_path: None,
            group_public_baseline: group_public_baseline.clone(),
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
                let history = self.dispatch_store().recent_messages(&conv.id, 60).await?;
                let ctx = ChatContext {
                    conversation_id: conv.id.clone(),
                    group_id: Some(conv.target_id.clone()),
                    group_settings: Some(settings.clone()),
                    history,
                    self_friend: member.clone(),
                    peers: vec![leader.clone()],
                    user_attachments: user_msg.attachments.clone(),
                    member_group_local_path: None,
                    group_public_baseline: group_public_baseline.clone(),
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
                workspace_id: None,
                attachments: &[],
            })
            .await?;
        self.emit(BusEvent::MessageCreated { message: msg });
        Ok(())
    }
}

fn excerpt_text(content: &str, max: usize) -> String {
    let t = content.trim();
    if t.chars().count() <= max {
        t.to_string()
    } else {
        format!("{}…", t.chars().take(max).collect::<String>())
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::BackendKind;

    fn agent(id: &str, name: &str) -> Friend {
        Friend {
            id: id.into(),
            name: name.into(),
            avatar: None,
            system_prompt: String::new(),
            personality: None,
            focus_tags: vec![],
            backend_kind: BackendKind::Api,
            backend_config: serde_json::json!({}),
            judge_provider_ref: None,
            enabled: true,
            is_builtin: false,
            active_workspace_id: None,
            profile: None,
            created_at: chrono::Utc::now(),
        }
    }

    fn user_msg(content: &str, mentions: Vec<String>) -> Message {
        Message {
            id: "m1".into(),
            conversation_id: "c".into(),
            turn_id: "t".into(),
            parent_id: None,
            sender_kind: SenderKind::User,
            sender_id: "u".into(),
            sender_name: "你".into(),
            content: content.into(),
            content_blocks: None,
            mentions,
            status: MessageStatus::Done,
            seen_by: vec![],
            model_used: None,
            tokens_in: None,
            tokens_out: None,
            on_behalf_of_user: false,
            workspace_id: None,
            attachments: vec![],
            created_at: chrono::Utc::now(),
        }
    }

    #[test]
    fn parse_at_mentions_from_coordinator_plan() {
        let agents = vec![agent("a", "Alice"), agent("b", "Bob")];
        let plan = "请 @Alice 写接口，@Bob 做测试";
        let got = parse_at_mention_assignees(plan, &agents);
        assert_eq!(got.len(), 2);
        assert_eq!(got[0].1, "Alice");
        assert_eq!(got[1].1, "Bob");
    }

    #[test]
    fn resolve_appointed_leader_by_at_in_content() {
        let agents = vec![agent("a", "Alice"), agent("b", "Bob")];
        let msg = user_msg("这个任务 @Bob 你来负责", vec![]);
        let got = resolve_appointed_leader(&msg, &agents);
        assert_eq!(got.map(|(id, _, _)| id), Some("b".into()));
    }

    #[test]
    fn resolve_appointed_leader_by_mention_id() {
        let agents = vec![agent("a", "Alice")];
        let msg = user_msg("你来", vec!["a".into()]);
        let got = resolve_appointed_leader(&msg, &agents);
        assert_eq!(got.map(|(id, name, _)| (id, name)), Some(("a".into(), "Alice".into())));
    }

    #[test]
    fn enrich_delegation_skips_leader_self() {
        let agents = vec![agent("l", "Lead"), agent("b", "Bob")];
        let ids = enrich_delegation_mentions("@Lead 统筹 @Bob 实现", &agents, Some("l"));
        assert_eq!(ids, vec!["b"]);
    }
}
