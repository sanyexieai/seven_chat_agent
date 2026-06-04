use std::collections::HashMap;
use std::sync::Arc;

use futures::StreamExt;
use serde::{Deserialize, Serialize};
use tokio::sync::broadcast;
use tracing::error;
use uuid::Uuid;

use crate::agent::{AgentEvent, AgentHandle, AgentRegistry, ChatContext};
use crate::assistant_intent::parse_quick_intent;
use crate::assistant_task_planner::{PlannedTaskAction, ReminderSchedule, plan_from_intent};
use crate::judge::{JudgeMode, JudgeService, JudgeSource, Judgment};
use crate::domain::{
    BackendKind, CliBlockDelta, ConvKind, Conversation, Friend, Group, GroupSettings, Message,
    MessageStatus, SenderKind,
};

/// 专家接话 prompt 场景（群聊自由讨论 vs 任务流执行协作）。
#[derive(Debug, Clone, Copy)]
pub(super) enum ExpertReplyMode {
    GroupChat,
    TaskFlowExecute,
}
use worker_bee_cli::{apply_cli_block_delta, cli_blocks_to_plain};
use crate::scheduler::{CandidateInfo, ScheduleDecision, SpeakerScheduler};
use crate::store::memory::NewMemory;
use crate::attachment::{content_with_attachments, validate_attachments};
use crate::domain::MessageAttachment;
use crate::store::message::NewMessage;
use crate::store::SqliteStore;
use crate::{Error, Result};

mod assistant_autonomy;
mod assistant_delegate;
mod im_writeback;
mod task_flow;

pub use im_writeback::ImWritebackEvent;

use assistant_delegate::{
    expert_friends_for_group, DelegateTaskHint, GroupAssistantPhase, StreamReplyOptions,
};
use task_flow::TaskFlowExecuteOutcome;
use crate::provider::ProviderRegistry;

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
    /// 群代理人将需主人知悉的事项写入备忘录后，推送给前端（不阻断群内 Agent）。
    AssistantOwnerNotify {
        conversation_id: String,
        group_id: String,
        group_name: String,
        title: String,
        body: String,
        message_id: Option<String>,
    },
}

pub struct MessageDispatcher {
    store: Arc<SqliteStore>,
    agents: Arc<AgentRegistry>,
    judge: Arc<JudgeService>,
    providers: Arc<ProviderRegistry>,
    tx: broadcast::Sender<BusEvent>,
    scheduler: SpeakerScheduler,
}

impl MessageDispatcher {
    pub fn new(
        store: Arc<SqliteStore>,
        agents: Arc<AgentRegistry>,
        judge: Arc<JudgeService>,
        providers: Arc<ProviderRegistry>,
    ) -> Self {
        let (tx, _) = broadcast::channel(1024);
        Self {
            store,
            agents,
            judge,
            providers,
            tx,
            scheduler: SpeakerScheduler::new(),
        }
    }

    /// 当前 dispatch 任务绑定的 tenant store（无绑定时用进程默认 tenant）。
    pub(crate) fn dispatch_store(&self) -> SqliteStore {
        let tid = crate::tenant_context::active_tenant_or(self.store.tenant_id());
        let mut scoped = self.store.for_tenant(&tid);
        if let Some(uid) = crate::tenant_context::active_user_id() {
            scoped = scoped.for_user(uid);
        }
        scoped
    }

    async fn conversation_tenant_id(&self, conversation_id: &str) -> Result<String> {
        if let Some(tid) = self.store.conversation_tenant_id(conversation_id).await? {
            return Ok(tid);
        }
        Ok(self.store.tenant_id().to_string())
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
        self.send_user_message_with_attachments(conversation_id, content, &[])
            .await
    }

    pub async fn send_user_message_with_attachments(
        &self,
        conversation_id: &str,
        content: &str,
        attachments: &[MessageAttachment],
    ) -> Result<Message> {
        let tenant_id = self.conversation_tenant_id(conversation_id).await?;
        let user_id = crate::tenant_context::active_user_id();
        crate::tenant_context::with_active_scope(&tenant_id, user_id.as_deref(), || {
            self.send_user_message_with_attachments_scoped(conversation_id, content, attachments)
        })
        .await
    }

    async fn send_user_message_with_attachments_scoped(
        &self,
        conversation_id: &str,
        content: &str,
        attachments: &[MessageAttachment],
    ) -> Result<Message> {
        let data_dir = std::env::var("SEVEN_CHAT_AGENT_DATA").unwrap_or_else(|_| "data".into());
        validate_attachments(&data_dir, conversation_id, attachments)?;
        let body = content_with_attachments(content, attachments);
        if body.trim().is_empty() && attachments.is_empty() {
            return Err(crate::Error::bad_request("消息不能为空"));
        }
        self.send_message_from_with_attachments(
            conversation_id,
            SenderKind::User,
            "user",
            "我",
            &body,
            attachments,
        )
        .await
    }

    pub async fn send_human_message(
        &self,
        conversation_id: &str,
        human_friend_id: &str,
        content: &str,
    ) -> Result<Message> {
        let tenant_id = self.conversation_tenant_id(conversation_id).await?;
        crate::tenant_context::with_active_tenant(&tenant_id, || async {
            let friend = self
                .dispatch_store()
                .get_friend(human_friend_id)
                .await?
                .ok_or_else(|| Error::not_found("human friend"))?;
            self.send_message_from_with_attachments(
                conversation_id,
                SenderKind::Friend,
                human_friend_id,
                &friend.name,
                content,
                &[],
            )
            .await
        })
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
        self.send_message_from_with_attachments(
            conversation_id,
            sender_kind,
            sender_id,
            sender_name,
            content,
            &[],
        )
        .await
    }

    async fn send_message_from_with_attachments(
        &self,
        conversation_id: &str,
        sender_kind: SenderKind,
        sender_id: &str,
        sender_name: &str,
        content: &str,
        attachments: &[MessageAttachment],
    ) -> Result<Message> {
        let tenant_id = self.conversation_tenant_id(conversation_id).await?;
        let conv = self
            .store
            .for_tenant(&tenant_id)
            .get_conversation_internal(conversation_id)
            .await?
            .ok_or_else(|| Error::not_found("conversation"))?;
        let scope_user = conv.scope_user_id.clone();
        crate::tenant_context::with_active_scope(
            &tenant_id,
            scope_user.as_deref(),
            || {
                self.send_message_from_with_attachments_scoped(
                    &conv,
                    sender_kind,
                    sender_id,
                    sender_name,
                    content,
                    attachments,
                )
            },
        )
        .await
    }

    async fn send_message_from_with_attachments_scoped(
        &self,
        conv: &Conversation,
        sender_kind: SenderKind,
        sender_id: &str,
        sender_name: &str,
        content: &str,
        attachments: &[MessageAttachment],
    ) -> Result<Message> {
        let turn_id = Uuid::new_v4().to_string();
        let store = self.dispatch_store();
        let msg = store
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
                on_behalf_of_user: false,
                workspace_id: None,
                attachments,
            })
            .await?;
        if sender_kind == SenderKind::User {
            self.observe_user_message_for_builtin_assistant(&conv, &msg)
                .await;
        }
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
                    if self
                        .maybe_handle_builtin_intent_in_dm(&conv, &turn_id, content)
                        .await?
                    {
                        self.scheduler.reset_turn(&turn_id);
                        self.emit(BusEvent::TurnEnded {
                            conversation_id: conv.id.clone(),
                            turn_id,
                        });
                        return Ok(msg);
                    }
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
            conversation_id: conv.id.clone(),
            turn_id,
        });
        Ok(msg)
    }

    async fn maybe_handle_builtin_intent_in_dm(
        &self,
        conv: &Conversation,
        turn_id: &str,
        content: &str,
    ) -> Result<bool> {
        let Some(builtin_id) = self.dispatch_store().builtin_assistant_id().await? else {
            return Ok(false);
        };
        if conv.target_id != builtin_id {
            return Ok(false);
        }
        let Some(intent) = parse_quick_intent(content) else {
            return Ok(false);
        };
        let plan = plan_from_intent(&builtin_id, intent);
        let mut created_todo: Option<crate::domain::AssistantTodo> = None;
        for action in &plan.actions {
            match action {
                PlannedTaskAction::CreateTodo {
                    title,
                    detail,
                    repeat_rule,
                    next_run_at,
                    priority,
                } => {
                    let todo = self
                        .store
                        .create_assistant_todo(
                            &builtin_id,
                            title,
                            detail.as_deref().filter(|x| !x.trim().is_empty()),
                            repeat_rule.as_deref(),
                            next_run_at.as_deref(),
                            *priority,
                            None,
                        )
                        .await?;
                    created_todo = Some(todo);
                }
                PlannedTaskAction::EnqueueReminder {
                    assistant_id,
                    title,
                    detail,
                    schedule,
                } => {
                    let (delay_seconds, schedule_json) = match schedule {
                        ReminderSchedule::AfterSeconds(secs) => ((*secs).max(1), serde_json::Value::Null),
                        ReminderSchedule::DailyAt {
                            hour,
                            minute,
                            timezone,
                        } => (
                            next_daily_delay_seconds(*hour, *minute, timezone),
                            serde_json::json!({
                                "type": "daily_at",
                                "hour": hour,
                                "minute": minute,
                                "timezone": timezone,
                            }),
                        ),
                    };
                    let payload = serde_json::json!({
                        "assistant_id": assistant_id,
                        "title": title,
                        "detail": detail,
                        "schedule": schedule_json,
                        "todo_id": created_todo.as_ref().map(|t| t.id.clone()),
                    });
                    self.dispatch_store()
                        .enqueue_assistant_job(
                            "todo_reminder",
                            Some(&payload.to_string()),
                            delay_seconds,
                            3,
                        )
                        .await?;
                }
            }
        }
        let ack = if let Some(todo) = created_todo {
            format!("已创建提醒任务：{}（按计划触发）", todo.title)
        } else {
            "已处理你的提醒请求。".to_string()
        };
        let reply = self
            .store
            .insert_message(NewMessage {
                conversation_id: &conv.id,
                turn_id,
                parent_id: None,
                sender_kind: SenderKind::Friend,
                sender_id: &builtin_id,
                sender_name: "Hex 助理",
                content: &ack,
                mentions: &[],
                status: MessageStatus::Done,
                on_behalf_of_user: false,
                workspace_id: None,
                attachments: &[],
            })
            .await?;
        self.emit(BusEvent::MessageCreated { message: reply.clone() });
        self.emit(BusEvent::MessageDone { message: reply });
        Ok(true)
    }

    async fn dispatch_dm(
        &self,
        conv: Conversation,
        user_msg: Message,
        turn_id: String,
    ) -> Result<()> {
        let friend_id = conv.target_id.clone();
        let friend = self
            .dispatch_store()
            .get_friend(&friend_id)
            .await?
            .ok_or_else(|| Error::not_found("friend"))?;
        let agent = self.agents.get(&friend_id).await?;
        let history = self.dispatch_store().recent_messages(&conv.id, 40).await?;
        let ctx = ChatContext {
            conversation_id: conv.id.clone(),
            group_id: None,
            group_settings: None,
            history,
            self_friend: friend.clone(),
            peers: vec![],
            user_attachments: user_msg.attachments.clone(),
            member_group_local_path: None,
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
            let members = expert_friends_for_group(&self.dispatch_store(), &group.id).await?;
            let flow = self
                .run_task_flow(&conv, &user_msg, &turn_id, &settings, &members)
                .await?;
            if flow.handled {
                if let Some(checkpoint) = flow.checkpoint {
                    let task_hint = Self::delegate_task_hint(checkpoint.outcome);
                    let assistant_reply = self
                        .maybe_dispatch_group_assistant(
                            &conv.id,
                            &group,
                            &user_msg,
                            &turn_id,
                            GroupAssistantPhase::AfterExperts,
                            task_hint,
                        )
                        .await?;
                    if self
                        .should_resume_task_flow_after_delegate(
                            &settings,
                            checkpoint.outcome,
                            assistant_reply.as_ref(),
                            &user_msg.content,
                        )
                        .await?
                    {
                        let directive = assistant_reply
                            .as_ref()
                            .map(|m| m.content.as_str())
                            .unwrap_or("");
                        tracing::info!(
                            turn_id = %turn_id,
                            prior_outcome = ?checkpoint.outcome,
                            "task_flow: resuming after delegate autonomous continue"
                        );
                        let final_outcome = self
                            .resume_task_flow_after_delegate(
                                &conv,
                                &user_msg,
                                &turn_id,
                                &settings,
                                &checkpoint,
                                directive,
                            )
                            .await?;
                        if final_outcome != TaskFlowExecuteOutcome::Delivered {
                            tracing::info!(
                                turn_id = %turn_id,
                                final_outcome = ?final_outcome,
                                "task_flow: resume ended without delivery"
                            );
                        }
                    }
                }
                return Ok(());
            }
        }

        let mut frontier = vec![user_msg.clone()];

        while !frontier.is_empty() {
            let trigger = frontier.remove(0);
            let replies = self
                .dispatch_expert_round(
                    &conv,
                    &group,
                    &settings,
                    &trigger,
                    &turn_id,
                    ExpertReplyMode::GroupChat,
                )
                .await?;
            if settings.allow_agent_to_agent {
                frontier.extend(replies);
            }
        }

        if user_msg.sender_kind == SenderKind::User {
            self.maybe_dispatch_group_assistant(
                &conv.id,
                &group,
                &user_msg,
                &turn_id,
                GroupAssistantPhase::AfterExperts,
                DelegateTaskHint::Unknown,
            )
            .await?;
        }
        Ok(())
    }

    /// 对一条触发消息调度专家接话（judge → scheduler → 生成回复）。
    pub(super) async fn dispatch_expert_round(
        &self,
        conv: &Conversation,
        group: &Group,
        settings: &GroupSettings,
        trigger: &Message,
        turn_id: &str,
        mode: ExpertReplyMode,
    ) -> Result<Vec<Message>> {
        let member_configs = self
            .dispatch_store()
            .list_group_member_configs(&group.id)
            .await?;
        let override_by_friend: std::collections::HashMap<_, _> = member_configs
            .iter()
            .map(|c| (c.friend_id.clone(), c.judge_override.clone()))
            .collect();
        let mut members = Vec::new();
        for c in &member_configs {
            if !c.role.participates_in_expert_scheduling() {
                continue;
            }
            if let Some(f) = self.dispatch_store().get_friend(&c.friend_id).await? {
                if f.enabled {
                    members.push(f);
                }
            }
        }

        let history = self.dispatch_store().recent_messages(&conv.id, 60).await?;

        let candidates = self
            .judge_members(
                conv,
                settings,
                &history,
                &members,
                &override_by_friend,
                trigger,
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
                mode = ?mode,
                "group: judgment_decided"
            );
            self.emit(BusEvent::JudgmentDecided {
                conversation_id: conv.id.clone(),
                turn_id: turn_id.to_string(),
                friend_id: c.friend_id.clone(),
                friend_name: c.friend_name.clone(),
                should_reply: c.judgment.should_reply,
                confidence: c.judgment.confidence,
                reason: c.judgment.reason.clone(),
                judge_source: src,
                configured_judge_mode: configured_mode.to_string(),
            });
        }

        let parent_chain = self.chain_actors(trigger).await;
        let has_typing_human = self.has_typing_human(&members).await;
        let threshold = settings.effective_judge_threshold();
        let willing = candidates
            .iter()
            .filter(|c| c.judgment.should_reply && c.judgment.confidence >= threshold)
            .count() as u32;
        let recent_texts: Vec<String> = history.iter().map(|m| m.content.clone()).collect();
        let decisions = self.scheduler.rank(
            turn_id,
            settings,
            trigger,
            candidates,
            &parent_chain,
            has_typing_human,
            &recent_texts,
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
                mode = ?mode,
                "group: no member scheduled to reply (strict + fallback both empty)"
            );
            self.emit(BusEvent::SchedulerPicked {
                conversation_id: conv.id.clone(),
                turn_id: turn_id.to_string(),
                decisions: vec![],
                schedule_mode: schedule_mode.to_string(),
                configured_judge_mode: configured_mode.to_string(),
                willing_to_reply: willing,
                judge_threshold: threshold,
            });
            return Ok(vec![]);
        }
        tracing::info!(
            conversation_id = %conv.id,
            turn_id = %turn_id,
            configured_judge_mode = configured_mode,
            schedule_mode,
            willing_to_reply = willing,
            picked = ?decisions.iter().map(|d| &d.friend_name).collect::<Vec<_>>(),
            mode = ?mode,
            "group: scheduler_picked"
        );
        self.emit(BusEvent::SchedulerPicked {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.to_string(),
            decisions: decisions.clone(),
            schedule_mode: schedule_mode.to_string(),
            configured_judge_mode: configured_mode.to_string(),
            willing_to_reply: willing,
            judge_threshold: threshold,
        });

        let mut replies = Vec::new();
        for d in decisions {
            let friend = match self.dispatch_store().get_friend(&d.friend_id).await? {
                Some(f) => f,
                None => continue,
            };
            let agent = self.agents.get(&friend.id).await?;
            let peers: Vec<Friend> = members
                .iter()
                .filter(|m| m.id != friend.id)
                .cloned()
                .collect();
            let history = self.dispatch_store().recent_messages(&conv.id, 60).await?;
            let ctx = ChatContext {
                conversation_id: conv.id.clone(),
                group_id: Some(group.id.clone()),
                group_settings: Some(settings.clone()),
                history,
                self_friend: friend.clone(),
                peers,
                user_attachments: trigger.attachments.clone(),
                member_group_local_path: None,
            };
            if d.delay_ms > 0 {
                tokio::time::sleep(std::time::Duration::from_millis(d.delay_ms)).await;
            }
            let prompt = Self::build_expert_reply_prompt(mode, trigger, &friend);
            let reply = self
                .stream_one_reply(conv, trigger, turn_id, &friend, agent, ctx, &prompt, 0)
                .await?;
            if let Some(reply_msg) = reply {
                self.scheduler.record_reply(turn_id, &reply_msg.content);
                replies.push(reply_msg);
            }
        }
        Ok(replies)
    }

    fn build_expert_reply_prompt(mode: ExpertReplyMode, trigger: &Message, friend: &Friend) -> String {
        match mode {
            ExpertReplyMode::GroupChat => format!(
                "群里 [{}] 刚说：{}\n\n\
                接话规则：只有当你有**与上文不同的新进展**、**新观点**或**需要你去回答的具体疑问**时才回应；\
                若他人已问过/说过同样的事，不要重复换说法。没有新内容则不要硬接。\n\
                请简短回应。",
                trigger.sender_name, trigger.content
            ),
            ExpertReplyMode::TaskFlowExecute => format!(
                "【任务流·执行协作】负责人「{}」说：\n{}\n\n\
                你是「{}」。若负责人 @ 你、向你分配任务或提问，请给出**可执行的具体回应**（查代码、跑命令、提供信息等）；\
                若你有不同于上文的实质进展也可补充。不要重复空泛表态。\n\
                请简短回应。",
                trigger.sender_name, trigger.content, friend.name
            ),
        }
    }

    async fn judge_members(
        &self,
        _conv: &Conversation,
        settings: &GroupSettings,
        history: &[Message],
        members: &[Friend],
        override_by_friend: &std::collections::HashMap<
            String,
            Option<seven_chat_agent_judge::MemberJudgeOverride>,
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
                Some(pid) => self.dispatch_store().get_message(&pid).await.ok().flatten(),
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
        let typing = self.dispatch_store().list_typing_humans().await.unwrap_or_default();
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
        self.stream_one_reply_with_options(
            conv,
            parent,
            turn_id,
            friend,
            agent,
            ctx,
            prompt,
            StreamReplyOptions {
                on_behalf_of_user: false,
                final_status: MessageStatus::Done,
            },
        )
        .await
    }

    async fn stream_one_reply_with_options(
        &self,
        conv: &Conversation,
        parent: &Message,
        turn_id: &str,
        friend: &Friend,
        agent: AgentHandle,
        ctx: ChatContext,
        prompt: &str,
        opts: StreamReplyOptions,
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
                on_behalf_of_user: opts.on_behalf_of_user,
                workspace_id: None,
                attachments: &[],
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
                opts.final_status,
                model_used.as_deref(),
                tokens_in,
                tokens_out,
                blocks_for_store,
            )
            .await;
        if let Ok(Some(m)) = self.dispatch_store().get_message(&placeholder.id).await {
            self.emit(BusEvent::MessageDone {
                message: m.clone(),
            });
            return Ok(Some(m));
        }
        Ok(None)
    }

    /// 用户采纳/驳回群助理待确认草稿。
    pub async fn resolve_group_delegate(
        &self,
        conversation_id: &str,
        message_id: &str,
        approve: bool,
        content_override: Option<String>,
    ) -> Result<Message> {
        let tenant_id = self.conversation_tenant_id(conversation_id).await?;
        crate::tenant_context::with_active_tenant(&tenant_id, || async {
            let store = self.dispatch_store();
            let msg = store
                .get_message(message_id)
                .await?
                .ok_or_else(|| Error::not_found("message"))?;
            if msg.conversation_id != conversation_id {
                return Err(Error::bad_request("消息不属于该会话"));
            }
            let updated = store
                .resolve_delegate_message(message_id, approve, content_override.as_deref())
                .await?;
            self.emit(BusEvent::MessageDone {
                message: updated.clone(),
            });

            if let Ok(Some(conv)) = store.get_conversation(conversation_id).await {
                if conv.kind == ConvKind::Group {
                    if let Ok(Some(group)) = store.get_group(&conv.target_id).await {
                        let ast = store
                            .resolve_group_assistant_settings(&group.settings.assistant)
                            .await
                            .unwrap_or_else(|_| group.settings.assistant.clone());
                        let event = if approve {
                            ImWritebackEvent::DelegateApproved
                        } else {
                            ImWritebackEvent::DelegateRejected
                        };
                        im_writeback::spawn_im_writeback_notify(
                            group,
                            ast,
                            conversation_id.to_string(),
                            updated.clone(),
                            event,
                        );
                    }
                }
            }

            Ok(updated)
        })
        .await
    }

    async fn observe_user_message_for_builtin_assistant(&self, conv: &Conversation, msg: &Message) {
        let Ok(Some(assistant_id)) = self.dispatch_store().builtin_assistant_id().await else {
            return;
        };
        let Ok(global) = self.dispatch_store().get_assistant_global_settings().await else {
            return;
        };
        let allowed = match conv.kind {
            ConvKind::Dm => global.should_observe_dm(),
            ConvKind::Group => global.should_observe_group(),
        };
        if !allowed {
            return;
        }

        if conv.kind == ConvKind::Dm && conv.target_id == assistant_id {
            tracing::debug!("skip observe: builtin assistant dm (use extract/reflect)");
            return;
        }

        let body = msg.content.trim();
        match crate::memory_record_policy::evaluate_observe_message(body, &global) {
            crate::memory_record_policy::RecordDecision::Skip(reason) => {
                tracing::debug!(reason, "skip observe memory");
                return;
            }
            crate::memory_record_policy::RecordDecision::Record => {}
        }

        let scope = match conv.kind {
            ConvKind::Dm => {
                let friend_name = self
                    .store
                    .get_friend(&conv.target_id)
                    .await
                    .ok()
                    .flatten()
                    .map(|f| f.name)
                    .unwrap_or_else(|| "未知好友".to_string());
                format!("私聊:{friend_name}")
            }
            ConvKind::Group => {
                let group_name = self
                    .store
                    .get_group(&conv.target_id)
                    .await
                    .ok()
                    .flatten()
                    .map(|g| g.name)
                    .unwrap_or_else(|| "未知群聊".to_string());
                format!("群聊:{group_name}")
            }
        };

        let dedupe_secs = global.observe_dedupe_secs.max(1) as i64;
        if self
            .store
            .observe_recent_duplicate(&assistant_id, &scope, body, dedupe_secs)
            .await
            .unwrap_or(false)
        {
            tracing::debug!(scope = %scope, "skip observe memory: duplicate");
            return;
        }

        let max_chars = global.record_max_chars.max(80) as usize;
        let summary = format!(
            "[默认观察/{scope}] 用户:{}\n内容:{}",
            msg.sender_name,
            truncate_chars(body, max_chars)
        );
        let scope_key = crate::memory_tier::scope_for_observe(conv);
        if let Err(err) = self
            .store
            .insert_memory(NewMemory {
                owner_friend_id: assistant_id.clone(),
                kind: crate::assistant_accumulation::MEMORY_KIND_MEMO.to_string(),
                content: summary,
                source_message_id: Some(msg.id.clone()),
                weight: global.record_weight.clamp(0.05, 1.0),
                pinned: false,
                tier: crate::memory_tier::TIER_RAW.to_string(),
                scope: scope_key.scope,
                scope_ref: scope_key.scope_ref,
                importance: 0,
                status: crate::memory_tier::STATUS_ACTIVE.to_string(),
                title: None,
                summary: None,
                expires_at: None,
                workspace_id: None,
            })
            .await
        {
            tracing::warn!(err = %err, "assistant observe memory insert failed");
            return;
        }
        if let Err(err) = self
            .store
            .touch_observe_consolidate(&assistant_id, &global)
            .await
        {
            tracing::debug!(err = %err, "assistant observe consolidate tick failed");
        }
    }

    /// 外部 IM 入站：用户发言或确认助理草稿。
    pub async fn handle_group_im_inbound(
        &self,
        group_id: &str,
        secret: &str,
        action: &str,
        content: Option<String>,
        message_id: Option<String>,
    ) -> Result<Message> {
        let group = self
            .store
            .get_group(group_id)
            .await?
            .ok_or_else(|| Error::not_found("group"))?;
        let ast = self
            .store
            .resolve_group_assistant_settings(&group.settings.assistant)
            .await?;
        let expected = ast
            .im_writeback
            .inbound_secret
            .as_deref()
            .filter(|s| !s.is_empty())
            .ok_or_else(|| Error::bad_request("该群未配置 IM 入站密钥"))?;
        if secret != expected {
            return Err(Error::bad_request("IM 入站密钥无效"));
        }

        let conv = self.dispatch_store().get_or_create_group_conversation(group_id).await?;

        match action {
            "user_message" => {
                let text = content
                    .filter(|s| !s.trim().is_empty())
                    .ok_or_else(|| Error::bad_request("user_message 需要 content"))?;
                self.send_user_message(&conv.id, &text).await
            }
            "approve_delegate" | "reject_delegate" => {
                let mid = message_id
                    .ok_or_else(|| Error::bad_request("需要 message_id"))?;
                let approve = action == "approve_delegate";
                self.resolve_group_delegate(&conv.id, &mid, approve, content)
                    .await
            }
            _ => Err(Error::bad_request(format!("未知 action: {action}"))),
        }
    }
}

fn next_daily_delay_seconds(hour: u32, minute: u32, timezone: &str) -> i64 {
    use chrono::{Datelike, Duration, TimeZone, Utc};
    let offset_seconds = match timezone {
        "UTC" | "Etc/UTC" => 0,
        _ => 8 * 3600,
    };
    let offset = chrono::FixedOffset::east_opt(offset_seconds)
        .unwrap_or_else(|| chrono::FixedOffset::east_opt(8 * 3600).expect("valid offset"));
    let now_utc = Utc::now();
    let now_local = now_utc.with_timezone(&offset);
    let mut next = offset
        .with_ymd_and_hms(
            now_local.year(),
            now_local.month(),
            now_local.day(),
            hour.min(23),
            minute.min(59),
            0,
        )
        .single()
        .unwrap_or(now_local + Duration::minutes(1));
    if next <= now_local {
        next += Duration::days(1);
    }
    (next.with_timezone(&Utc) - now_utc).num_seconds().max(1)
}

fn judge_mode_label(mode: JudgeMode) -> &'static str {
    match mode {
        JudgeMode::Heuristic => "heuristic",
        JudgeMode::Llm => "llm",
        JudgeMode::Auto => "auto",
    }
}

fn truncate_chars(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        return s.to_string();
    }
    let mut out: String = s.chars().take(max).collect();
    out.push('…');
    out
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
