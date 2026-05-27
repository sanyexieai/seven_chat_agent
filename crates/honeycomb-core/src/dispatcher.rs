use std::collections::HashMap;
use std::sync::Arc;

use futures::StreamExt;
use serde::{Deserialize, Serialize};
use tokio::sync::broadcast;
use tracing::error;
use uuid::Uuid;

use crate::agent::{AgentEvent, AgentHandle, AgentRegistry, ChatContext};
use crate::judge::{JudgeMode, JudgeService, JudgeSource, Judgment};
use crate::domain::{
    BackendKind, CliBlockDelta, ConvKind, Conversation, Friend, GroupSettings, Message,
    MessageStatus, SenderKind,
};
use worker_bee_cli::{apply_cli_block_delta, cli_blocks_to_plain};
use crate::scheduler::{CandidateInfo, ScheduleDecision, SpeakerScheduler};
use crate::store::message::NewMessage;
use crate::store::SqliteStore;
use crate::{Error, Result};

mod task_flow;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum BusEvent {
    MessageCreated {
        message: Message,
    },
    MessageDelta {
        message_id: String,
        conversation_id: String,
        delta: String,
        thinking: bool,
    },
    MessageCliDelta {
        message_id: String,
        conversation_id: String,
        delta: CliBlockDelta,
    },
    MessageDone {
        message: Message,
    },
    MessageFailed {
        message_id: String,
        conversation_id: String,
        reason: String,
    },
    TurnStarted {
        conversation_id: String,
        turn_id: String,
    },
    TurnEnded {
        conversation_id: String,
        turn_id: String,
    },
    JudgmentDecided {
        conversation_id: String,
        turn_id: String,
        friend_id: String,
        friend_name: String,
        should_reply: bool,
        confidence: f32,
        reason: Option<String>,
        /// 实际 judge 通路：`llm` / `heuristic` / `llm_failed` / `auto_llm` / `auto_heuristic`
        judge_source: Option<String>,
        /// 群配置的模式：`llm` / `heuristic` / `auto`
        configured_judge_mode: String,
    },
    SchedulerPicked {
        conversation_id: String,
        turn_id: String,
        decisions: Vec<ScheduleDecision>,
        /// `strict` | `fallback` | `none`
        schedule_mode: String,
        configured_judge_mode: String,
        willing_to_reply: u32,
        judge_threshold: f32,
    },
    /// 任务流阶段：`campaign` | `election` | `execute`
    TaskFlowPhase {
        conversation_id: String,
        turn_id: String,
        phase: String,
        detail: Option<String>,
    },
    CampaignPitch {
        conversation_id: String,
        turn_id: String,
        friend_id: String,
        friend_name: String,
    },
    LeaderElected {
        conversation_id: String,
        turn_id: String,
        friend_id: String,
        friend_name: String,
        reason: String,
        confidence: f32,
        /// true = LLM 选举成功；false = 互投/选举失败后的兜底
        election_ok: bool,
        peer_votes_summary: Option<String>,
        pitches: Vec<(String, String)>,
    },
    PeerVote {
        conversation_id: String,
        turn_id: String,
        voter_id: String,
        voter_name: String,
        endorse_id: String,
        endorse_name: String,
        reason: String,
    },
    PeerVoteFailed {
        conversation_id: String,
        turn_id: String,
        voter_id: String,
        voter_name: String,
        error: String,
    },
    PlanPublished {
        conversation_id: String,
        turn_id: String,
        friend_id: String,
        friend_name: String,
        plan_excerpt: String,
    },
    PlanReview {
        conversation_id: String,
        turn_id: String,
        friend_id: String,
        friend_name: String,
        content: String,
    },
}

pub struct MessageDispatcher {
    store: Arc<SqliteStore>,
    agents: Arc<AgentRegistry>,
    judge: Arc<JudgeService>,
    tx: broadcast::Sender<BusEvent>,
    scheduler: SpeakerScheduler,
}

impl MessageDispatcher {
    pub fn new(
        store: Arc<SqliteStore>,
        agents: Arc<AgentRegistry>,
        judge: Arc<JudgeService>,
    ) -> Self {
        let (tx, _) = broadcast::channel(1024);
        Self {
            store,
            agents,
            judge,
            tx,
            scheduler: SpeakerScheduler::new(),
        }
    }

    pub fn subscribe(&self) -> broadcast::Receiver<BusEvent> {
        self.tx.subscribe()
    }

    pub fn emit(&self, event: BusEvent) {
        let _ = self.tx.send(event);
    }

    pub async fn send_user_message(
        &self,
        conversation_id: &str,
        content: &str,
    ) -> Result<Message> {
        self.send_message_from(conversation_id, SenderKind::User, "user", "我", content)
            .await
    }

    pub async fn send_human_message(
        &self,
        conversation_id: &str,
        human_friend_id: &str,
        content: &str,
    ) -> Result<Message> {
        let friend = self
            .store
            .get_friend(human_friend_id)
            .await?
            .ok_or_else(|| Error::not_found("human friend"))?;
        self.send_message_from(
            conversation_id,
            SenderKind::Friend,
            human_friend_id,
            &friend.name,
            content,
        )
        .await
    }

    async fn send_message_from(
        &self,
        conversation_id: &str,
        sender_kind: SenderKind,
        sender_id: &str,
        sender_name: &str,
        content: &str,
    ) -> Result<Message> {
        let conv = self
            .store
            .get_conversation(conversation_id)
            .await?
            .ok_or_else(|| Error::not_found("conversation"))?;
        let turn_id = Uuid::new_v4().to_string();
        let msg = self
            .store
            .insert_message(NewMessage {
                conversation_id: &conv.id,
                turn_id: &turn_id,
                parent_id: None,
                sender_kind,
                sender_id,
                sender_name,
                content,
                mentions: &[],
                status: MessageStatus::Done,
            })
            .await?;
        self.emit(BusEvent::MessageCreated {
            message: msg.clone(),
        });
        self.emit(BusEvent::TurnStarted {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.clone(),
        });

        match conv.kind {
            ConvKind::Dm => {
                if matches!(sender_kind, SenderKind::User) {
                    self.dispatch_dm(conv.clone(), msg.clone(), turn_id.clone())
                        .await?;
                }
            }
            ConvKind::Group => {
                self.dispatch_group(conv.clone(), msg.clone(), turn_id.clone())
                    .await?;
            }
        }
        self.scheduler.reset_turn(&turn_id);
        self.emit(BusEvent::TurnEnded {
            conversation_id: conv.id,
            turn_id,
        });
        Ok(msg)
    }

    async fn dispatch_dm(
        &self,
        conv: Conversation,
        user_msg: Message,
        turn_id: String,
    ) -> Result<()> {
        let friend_id = conv.target_id.clone();
        let friend = self
            .store
            .get_friend(&friend_id)
            .await?
            .ok_or_else(|| Error::not_found("friend"))?;
        let agent = self.agents.get(&friend_id).await?;
        let history = self.store.recent_messages(&conv.id, 40).await?;
        let ctx = ChatContext {
            conversation_id: conv.id.clone(),
            group_settings: None,
            history,
            self_friend: friend.clone(),
            peers: vec![],
        };
        self.stream_one_reply(&conv, &user_msg, &turn_id, &friend, agent, ctx, &user_msg.content, 0)
            .await?;
        Ok(())
    }

    async fn dispatch_group(
        &self,
        conv: Conversation,
        user_msg: Message,
        turn_id: String,
    ) -> Result<()> {
        let group = self
            .store
            .get_group(&conv.target_id)
            .await?
            .ok_or_else(|| Error::not_found("group"))?;
        let settings = group.settings.clone();

        if user_msg.sender_kind == SenderKind::User && settings.task_flow.enabled {
            let member_configs = self.store.list_group_member_configs(&group.id).await?;
            let mut members = Vec::new();
            for mid in member_configs.iter().map(|c| &c.friend_id) {
                if let Some(f) = self.store.get_friend(mid).await? {
                    if f.enabled {
                        members.push(f);
                    }
                }
            }
            if self
                .run_task_flow(&conv, &user_msg, &turn_id, &settings, &members)
                .await?
            {
                return Ok(());
            }
        }

        let mut frontier = vec![user_msg.clone()];

        while !frontier.is_empty() {
            let trigger = frontier.remove(0);
            let member_configs = self.store.list_group_member_configs(&group.id).await?;
            let override_by_friend: std::collections::HashMap<_, _> = member_configs
                .iter()
                .map(|c| (c.friend_id.clone(), c.judge_override.clone()))
                .collect();
            let mut members = Vec::new();
            for mid in member_configs.iter().map(|c| &c.friend_id) {
                if let Some(f) = self.store.get_friend(mid).await? {
                    if f.enabled {
                        members.push(f);
                    }
                }
            }

            let history = self.store.recent_messages(&conv.id, 60).await?;
            let triggers_self =
                trigger.sender_kind == SenderKind::User || matches!(trigger.sender_kind, SenderKind::Friend);

            let candidates = self
                .judge_members(
                    &conv,
                    &settings,
                    &history,
                    &members,
                    &override_by_friend,
                    &trigger,
                )
                .await;

            let configured_mode = judge_mode_label(settings.judge.mode);
            for c in &candidates {
                let src = judge_source_label(c.judgment.source);
                tracing::info!(
                    conversation_id = %conv.id,
                    turn_id = %turn_id,
                    friend = %c.friend_name,
                    configured_judge_mode = configured_mode,
                    judge_source = src.as_deref().unwrap_or("unknown"),
                    should_reply = c.judgment.should_reply,
                    confidence = c.judgment.confidence,
                    reason = ?c.judgment.reason,
                    "group: judgment_decided"
                );
                self.emit(BusEvent::JudgmentDecided {
                    conversation_id: conv.id.clone(),
                    turn_id: turn_id.clone(),
                    friend_id: c.friend_id.clone(),
                    friend_name: c.friend_name.clone(),
                    should_reply: c.judgment.should_reply,
                    confidence: c.judgment.confidence,
                    reason: c.judgment.reason.clone(),
                    judge_source: src,
                    configured_judge_mode: configured_mode.to_string(),
                });
            }

            let parent_chain = self.chain_actors(&trigger).await;
            let has_typing_human = self.has_typing_human(&members).await;
            let threshold = settings.effective_judge_threshold();
            let willing = candidates
                .iter()
                .filter(|c| c.judgment.should_reply && c.judgment.confidence >= threshold)
                .count() as u32;
            let decisions = self.scheduler.rank(
                &turn_id,
                &settings,
                &trigger,
                candidates,
                &parent_chain,
                has_typing_human,
            );
            let schedule_mode = if decisions.is_empty() {
                "none"
            } else if decisions[0]
                .reason
                .as_deref()
                .is_some_and(|r| r.contains("兜底"))
            {
                "fallback"
            } else {
                "strict"
            };
            if decisions.is_empty() {
                tracing::info!(
                    conversation_id = %conv.id,
                    group_id = %group.id,
                    member_count = members.len(),
                    configured_judge_mode = configured_mode,
                    willing_to_reply = willing,
                    judge_threshold = threshold,
                    schedule_mode,
                    "group: no member scheduled to reply (strict + fallback both empty)"
                );
                self.emit(BusEvent::SchedulerPicked {
                    conversation_id: conv.id.clone(),
                    turn_id: turn_id.clone(),
                    decisions: vec![],
                    schedule_mode: schedule_mode.to_string(),
                    configured_judge_mode: configured_mode.to_string(),
                    willing_to_reply: willing,
                    judge_threshold: threshold,
                });
                let _ = triggers_self;
                continue;
            }
            tracing::info!(
                conversation_id = %conv.id,
                turn_id = %turn_id,
                configured_judge_mode = configured_mode,
                schedule_mode,
                willing_to_reply = willing,
                picked = ?decisions.iter().map(|d| &d.friend_name).collect::<Vec<_>>(),
                "group: scheduler_picked"
            );
            self.emit(BusEvent::SchedulerPicked {
                conversation_id: conv.id.clone(),
                turn_id: turn_id.clone(),
                decisions: decisions.clone(),
                schedule_mode: schedule_mode.to_string(),
                configured_judge_mode: configured_mode.to_string(),
                willing_to_reply: willing,
                judge_threshold: threshold,
            });

            for d in decisions {
                let friend = match self.store.get_friend(&d.friend_id).await? {
                    Some(f) => f,
                    None => continue,
                };
                let agent = self.agents.get(&friend.id).await?;
                let peers: Vec<Friend> = members
                    .iter()
                    .filter(|m| m.id != friend.id)
                    .cloned()
                    .collect();
                let history = self.store.recent_messages(&conv.id, 60).await?;
                let ctx = ChatContext {
                    conversation_id: conv.id.clone(),
                    group_settings: Some(settings.clone()),
                    history,
                    self_friend: friend.clone(),
                    peers,
                };
                if d.delay_ms > 0 {
                    tokio::time::sleep(std::time::Duration::from_millis(d.delay_ms)).await;
                }
                let prompt = format!(
                    "群里 [{}] 刚说：{}\n请按你的人设给出一句自然回应。",
                    trigger.sender_name, trigger.content
                );
                let reply = self
                    .stream_one_reply(&conv, &trigger, &turn_id, &friend, agent, ctx, &prompt, 0)
                    .await?;
                if let Some(reply_msg) = reply {
                    self.scheduler.record_reply(&turn_id, &reply_msg.content);
                    if settings.allow_agent_to_agent {
                        frontier.push(reply_msg);
                    }
                }
            }
        }
        Ok(())
    }

    async fn judge_members(
        &self,
        _conv: &Conversation,
        settings: &GroupSettings,
        history: &[Message],
        members: &[Friend],
        override_by_friend: &std::collections::HashMap<
            String,
            Option<honeycomb_judge::MemberJudgeOverride>,
        >,
        trigger: &Message,
    ) -> Vec<CandidateInfo> {
        let mut handles = Vec::new();
        for m in members {
            if m.id == trigger.sender_id {
                continue;
            }
            let m = m.clone();
            let judge = self.judge.clone();
            let history = history.to_vec();
            let trig = trigger.clone();
            let settings = settings.clone();
            let member_override = override_by_friend.get(&m.id).cloned().flatten();
            handles.push(tokio::spawn(async move {
                let judgment = match m.backend_kind {
                    BackendKind::Human => Judgment {
                        should_reply: false,
                        confidence: 0.0,
                        reason: Some("真人成员不参与自动 judge".into()),
                        suggested_delay_ms: 0,
                        source: None,
                    },
                    _ => {
                        judge
                            .evaluate_member(
                                &settings,
                                &m,
                                member_override.as_ref(),
                                &history,
                                &trig,
                            )
                            .await
                    }
                };
                CandidateInfo {
                    friend_id: m.id,
                    friend_name: m.name,
                    backend_kind: m.backend_kind,
                    judgment,
                }
            }));
        }
        let mut out = Vec::new();
        for h in handles {
            if let Ok(c) = h.await {
                out.push(c);
            }
        }
        out
    }

    async fn chain_actors(&self, msg: &Message) -> HashMap<String, u32> {
        let mut counts: HashMap<String, u32> = HashMap::new();
        let mut cur = Some(msg.clone());
        while let Some(m) = cur {
            if m.sender_kind == SenderKind::Friend {
                *counts.entry(m.sender_id.clone()).or_insert(0) += 1;
            }
            cur = match m.parent_id {
                Some(pid) => self.store.get_message(&pid).await.ok().flatten(),
                None => None,
            };
        }
        counts
    }

    async fn has_typing_human(&self, members: &[Friend]) -> bool {
        let human_ids: Vec<String> = members
            .iter()
            .filter(|m| m.backend_kind == BackendKind::Human)
            .map(|m| m.id.clone())
            .collect();
        if human_ids.is_empty() {
            return false;
        }
        let typing = self.store.list_typing_humans().await.unwrap_or_default();
        typing.into_iter().any(|id| human_ids.contains(&id))
    }

    async fn stream_one_reply(
        &self,
        conv: &Conversation,
        parent: &Message,
        turn_id: &str,
        friend: &Friend,
        agent: AgentHandle,
        ctx: ChatContext,
        prompt: &str,
        _depth: usize,
    ) -> Result<Option<Message>> {
        let placeholder = self
            .store
            .insert_message(NewMessage {
                conversation_id: &conv.id,
                turn_id,
                parent_id: Some(&parent.id),
                sender_kind: SenderKind::Friend,
                sender_id: &friend.id,
                sender_name: &friend.name,
                content: "",
                mentions: &[],
                status: MessageStatus::Streaming,
            })
            .await?;
        self.emit(BusEvent::MessageCreated {
            message: placeholder.clone(),
        });

        let mut stream = match agent.send(ctx, prompt.to_string()).await {
            Ok(s) => s,
            Err(e) => {
                let preset = friend
                    .backend_config
                    .get("preset")
                    .and_then(|v| v.as_str())
                    .unwrap_or("(missing)");
                error!(
                    friend_id = %friend.id,
                    friend_name = %friend.name,
                    preset = %preset,
                    err = %e,
                    "agent.send failed"
                );
                let _ = self
                    .store
                    .finalize_message(
                        &placeholder.id,
                        &format!("(error: {e})"),
                        MessageStatus::Failed,
                        None,
                        None,
                        None,
                        None,
                    )
                    .await;
                self.emit(BusEvent::MessageFailed {
                    message_id: placeholder.id.clone(),
                    conversation_id: conv.id.clone(),
                    reason: e.to_string(),
                });
                return Ok(None);
            }
        };

        let mut content = String::new();
        let mut content_blocks: Vec<worker_bee_cli::CliBlock> = Vec::new();
        let mut model_used: Option<String> = None;
        let mut tokens_in: Option<i64> = None;
        let mut tokens_out: Option<i64> = None;
        let mut failed_reason: Option<String> = None;

        while let Some(ev) = stream.next().await {
            match ev {
                AgentEvent::Token(t) => {
                    content.push_str(&t);
                    self.emit(BusEvent::MessageDelta {
                        message_id: placeholder.id.clone(),
                        conversation_id: conv.id.clone(),
                        delta: t,
                        thinking: false,
                    });
                }
                AgentEvent::CliDelta(delta) => {
                    apply_cli_block_delta(&mut content_blocks, &delta);
                    content = cli_blocks_to_plain(&content_blocks);
                    self.emit(BusEvent::MessageCliDelta {
                        message_id: placeholder.id.clone(),
                        conversation_id: conv.id.clone(),
                        delta,
                    });
                }
                AgentEvent::Thinking(t) => {
                    self.emit(BusEvent::MessageDelta {
                        message_id: placeholder.id.clone(),
                        conversation_id: conv.id.clone(),
                        delta: t,
                        thinking: true,
                    });
                }
                AgentEvent::Tool { .. } => {}
                AgentEvent::WaitingHuman { .. } => {}
                AgentEvent::Done(info) => {
                    model_used = info.model.clone();
                    tokens_in = Some(info.tokens_in);
                    tokens_out = Some(info.tokens_out);
                }
                AgentEvent::Error(e) => {
                    failed_reason = Some(e);
                }
            }
        }

        let blocks_for_store = if content_blocks.is_empty() {
            None
        } else {
            Some(content_blocks.as_slice())
        };

        if let Some(reason) = failed_reason {
            let _ = self
                .store
                .finalize_message(
                    &placeholder.id,
                    &content,
                    MessageStatus::Failed,
                    model_used.as_deref(),
                    tokens_in,
                    tokens_out,
                    blocks_for_store,
                )
                .await;
            self.emit(BusEvent::MessageFailed {
                message_id: placeholder.id.clone(),
                conversation_id: conv.id.clone(),
                reason,
            });
            return Ok(None);
        }

        let _ = self
            .store
            .finalize_message(
                &placeholder.id,
                &content,
                MessageStatus::Done,
                model_used.as_deref(),
                tokens_in,
                tokens_out,
                blocks_for_store,
            )
            .await;
        if let Ok(Some(m)) = self.store.get_message(&placeholder.id).await {
            self.emit(BusEvent::MessageDone {
                message: m.clone(),
            });
            return Ok(Some(m));
        }
        Ok(None)
    }
}

fn judge_mode_label(mode: JudgeMode) -> &'static str {
    match mode {
        JudgeMode::Heuristic => "heuristic",
        JudgeMode::Llm => "llm",
        JudgeMode::Auto => "auto",
    }
}

fn judge_source_label(source: Option<JudgeSource>) -> Option<String> {
    source.map(|s| match s {
        JudgeSource::Heuristic => "heuristic",
        JudgeSource::Llm => "llm",
        JudgeSource::LlmFailed => "llm_failed",
        JudgeSource::AutoLlm => "auto_llm",
        JudgeSource::AutoHeuristic => "auto_heuristic",
    }.to_string())
}
