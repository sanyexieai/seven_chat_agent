pub mod attachment;
pub mod env;
pub mod assistant_accumulation;
pub mod llm_json;
pub mod memory_embedding;
pub mod memory_ingest;
pub mod memory_maintenance;
pub mod memory_record_policy;
pub mod memory_tier;
pub mod assistant_intent;
pub mod assistant_task_planner;
pub mod agent;
pub use seven_chat_agent_cli;
pub mod cli_auth;
pub mod cli_relay;
pub mod cli_tool;
pub mod cli_transcript;
pub mod cli_workspace;
pub mod friend_cli;
pub mod runtime;
pub mod config;
pub mod dispatcher;
pub mod domain;
pub mod group_validate;
pub mod error;
pub mod judge;
pub mod provider;
pub mod scheduler;
pub mod store;

pub use cli_auth::{CliAuthStatus, CliOAuthManager, CliOAuthPhase, CliOAuthSnapshot};
pub use cli_relay::{RelayHub, RelayJobSpec, RelayNodeInfo};
pub use error::{Error, Result};

use std::sync::Arc;

use crate::agent::AgentRegistry;
use crate::assistant_task_planner::{AssistantTaskPlan, PlannedTaskAction, ReminderSchedule};
use crate::dispatcher::MessageDispatcher;
use crate::domain::{MessageStatus, SenderKind};
use crate::provider::ProviderRegistry;
use crate::store::SqliteStore;

#[derive(Clone)]
pub struct SevenChatAgent {
    pub store: Arc<SqliteStore>,
    pub providers: Arc<ProviderRegistry>,
    pub agents: Arc<AgentRegistry>,
    pub dispatcher: Arc<MessageDispatcher>,
    pub cli_oauth: Arc<CliOAuthManager>,
    pub cli_relay: Arc<RelayHub>,
}

#[derive(Debug, Clone)]
pub enum AssistantQueueTask {
    IdleTick,
    SyncSkills,
    ConsolidateMemory,
}

impl SevenChatAgent {
    pub async fn boot(database_url: &str) -> Result<Self> {
        let store = Arc::new(SqliteStore::connect(database_url).await?);
        store.migrate().await?;
        store.migrate_fixup_provider_display_names().await?;
        store.migrate_legacy_assistant_friends().await?;
        store.migrate_fixup_pty_worker_bee_configs().await?;
        store.migrate_fixup_unconfigured_pty_friends().await?;
        store.seed_builtins().await?;
        store.migrate_ensure_group_assistants().await?;
        store.seed_assistant_policy_templates().await?;
        store.ensure_tenant().await?;
        store.ensure_assistant_global_settings().await?;
        store.migrate_all_friend_workspaces().await?;
        store.migrate_legacy_workspace_cli_sessions().await?;
        let _ = store.repair_recurring_todos().await;

        let providers = Arc::new(ProviderRegistry::new(store.clone()).await?);
        let judge = Arc::new(crate::judge::JudgeService::new(providers.clone()));
        let cli_relay = RelayHub::new();
        let agents = Arc::new(AgentRegistry::new(
            store.clone(),
            providers.clone(),
            judge.clone(),
            cli_relay.clone(),
        ));
        let dispatcher = Arc::new(MessageDispatcher::new(
            store.clone(),
            agents.clone(),
            judge,
            providers.clone(),
        ));

        let core = Self {
            store,
            providers,
            agents,
            dispatcher,
            cli_oauth: Arc::new(CliOAuthManager::new()),
            cli_relay,
        };
        core.spawn_assistant_queue_worker();
        Ok(core)
    }

    fn spawn_assistant_queue_worker(&self) {
        let core = self.clone();
        tokio::spawn(async move {
            loop {
                if let Err(e) = core.process_assistant_queue_once().await {
                    tracing::debug!(err = %e, "assistant queue worker tick failed");
                }
                let sleep_for = match core.store.next_due_assistant_job_at().await {
                    Ok(Some(next_at)) => {
                        let now = chrono::Utc::now();
                        if next_at <= now {
                            std::time::Duration::from_millis(150)
                        } else {
                            (next_at - now)
                                .to_std()
                                .unwrap_or_else(|_| std::time::Duration::from_millis(150))
                        }
                    }
                    Ok(None) => std::time::Duration::from_secs(5),
                    Err(_) => std::time::Duration::from_secs(2),
                };
                tokio::time::sleep(sleep_for).await;
            }
        });
    }

    pub async fn enqueue_assistant_task(&self, task: AssistantQueueTask) -> Result<()> {
        self.enqueue_assistant_task_after(task, 0).await
    }

    pub async fn enqueue_assistant_task_after(
        &self,
        task: AssistantQueueTask,
        delay_seconds: i64,
    ) -> Result<()> {
        let kind = match task {
            AssistantQueueTask::IdleTick => "idle_tick",
            AssistantQueueTask::SyncSkills => "sync_skills",
            AssistantQueueTask::ConsolidateMemory => "consolidate_memory",
        };
        self.store
            .enqueue_assistant_job(kind, None, delay_seconds, 3)
            .await?;
        Ok(())
    }

    pub async fn execute_assistant_task_plan(
        &self,
        owner_friend_id: &str,
        plan: &AssistantTaskPlan,
    ) -> Result<Option<crate::domain::AssistantTodo>> {
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
                            owner_friend_id,
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
                    self.store
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
        Ok(created_todo)
    }

    async fn process_assistant_queue_once(&self) -> Result<()> {
        let jobs = self.store.fetch_due_assistant_jobs(16).await?;
        for job in jobs {
            self.store.mark_assistant_job_running(&job.id).await?;
            let run = match job.kind.as_str() {
                "idle_tick" => {
                    let result = self.run_assistant_idle_tick().await.map(|_| ());
                    let _ = self
                        .enqueue_assistant_task_after(AssistantQueueTask::IdleTick, 45)
                        .await;
                    result
                }
                "sync_skills" => self.run_assistant_sync_skills().await,
                "consolidate_memory" => self.run_assistant_consolidate().await,
                "todo_reminder" => self
                    .run_assistant_todo_reminder(job.payload.as_deref())
                    .await,
                _ => Err(Error::bad_request(format!("unknown queue task kind {}", job.kind))),
            };
            match run {
                Ok(()) => self.store.mark_assistant_job_done(&job.id).await?,
                Err(e) => self
                    .store
                    .mark_assistant_job_failed_or_retry(&job, &e.to_string())
                    .await?,
            }
        }
        Ok(())
    }

    /// 空闲守护：生成并处理助理待办。
    pub async fn run_assistant_idle_tick(&self) -> Result<usize> {
        use crate::assistant_accumulation::{MEMORY_KIND_MEMO, truncate_chars};
        use crate::domain::AssistantTodoStatus;
        use crate::store::memory::NewMemory;

        let settings = self.store.get_assistant_global_settings().await?;
        if !settings.proactive_enabled || !self.store.assistant_budget_available(&settings) {
            return Ok(0);
        }
        let Some(assistant_id) = self.store.builtin_assistant_id().await? else {
            return Ok(0);
        };

        let pending_all = self
            .store
            .list_assistant_todos(
                &assistant_id,
                Some(AssistantTodoStatus::Pending),
                settings.proactive_batch_size.max(1) as i64,
            )
            .await?;
        let mut pending: Vec<_> = pending_all
            .into_iter()
            .filter(|t| t.repeat_rule.is_none())
            .collect();

        if pending.is_empty() {
            let has_repeat_pending = self
                .store
                .list_assistant_todos(
                    &assistant_id,
                    Some(AssistantTodoStatus::Pending),
                    200,
                )
                .await?
                .into_iter()
                .any(|t| t.repeat_rule.is_some());
            if !has_repeat_pending {
                let _ = self
                    .store
                    .create_assistant_todo(
                        &assistant_id,
                        "空闲巡检：知识与工具同步",
                        Some("检查知识沉淀质量、同步技能目录并清理低价值记忆"),
                        None,
                        None,
                        1,
                        None,
                    )
                    .await?;
                pending = self
                    .store
                    .list_assistant_todos(
                        &assistant_id,
                        Some(AssistantTodoStatus::Pending),
                        settings.proactive_batch_size.max(1) as i64,
                    )
                    .await?
                    .into_iter()
                    .filter(|t| t.repeat_rule.is_none())
                    .collect();
            }
        }

        let delegate_friends = if settings.proactive_delegate_enabled {
            let all = self.store.list_friends().await.unwrap_or_default();
            all.into_iter()
                .filter(|f| {
                    f.enabled
                        && !f.is_builtin
                        && matches!(
                            f.backend_kind,
                            crate::domain::BackendKind::Pty | crate::domain::BackendKind::Api
                        )
                        && (settings.proactive_delegate_friend_ids.is_empty()
                            || settings
                                .proactive_delegate_friend_ids
                                .iter()
                                .any(|id| id == &f.id))
                })
                .collect::<Vec<_>>()
        } else {
            Vec::new()
        };

        let mut processed = 0usize;
        for t in pending {
            self.store
                .update_assistant_todo_status(&t.id, AssistantTodoStatus::Running)
                .await?;
            let mut execute_note = String::from("由内置助理自主执行");
            let run_result: Result<()> = async {
                if let Some(friend) = delegate_friends.get(processed % delegate_friends.len().max(1)) {
                    execute_note = format!("已调度 agent 好友「{}」执行", friend.name);
                    let conv = self.store.get_or_create_dm(&friend.id).await?;
                    let task_prompt = format!(
                        "【系统调度任务】请执行以下待办：\n标题：{}\n优先级：{}\n说明：{}",
                        t.title,
                        t.priority,
                        t.detail.as_deref().unwrap_or("（无）")
                    );
                    let _ = self
                        .dispatcher
                        .send_user_message(&conv.id, &task_prompt)
                        .await;
                } else {
                    if let Ok(Some(dir)) = self.store.builtin_assistant_skills_dir().await {
                        let _ = self.store.sync_skills_from_disk(&assistant_id, &dir).await;
                    }
                    let _ = self.store.consolidate_memories(&assistant_id).await;
                }
                Ok(())
            }
            .await;
            let (status, tag) = if run_result.is_ok() {
                (AssistantTodoStatus::Done, "[待办执行]")
            } else {
                (AssistantTodoStatus::Failed, "[待办失败]")
            };
            let _ = self
                .store
                .insert_memory(NewMemory {
                    owner_friend_id: assistant_id.clone(),
                    kind: MEMORY_KIND_MEMO.to_string(),
                    content: format!(
                        "{} {}\n{}\n{}",
                        tag,
                        t.title,
                        execute_note,
                        truncate_chars(t.detail.as_deref().unwrap_or(""), 160)
                    ),
                    source_message_id: None,
                    weight: 0.35,
                    pinned: false,
                    tier: crate::memory_tier::TIER_RAW.to_string(),
                    scope: crate::memory_tier::SCOPE_GLOBAL.to_string(),
                    scope_ref: None,
                    importance: 0,
                    status: crate::memory_tier::STATUS_ACTIVE.to_string(),
                    title: None,
                    summary: None,
                    expires_at: None,
                    workspace_id: None,
                })
                .await;
            self.store.update_assistant_todo_status(&t.id, status).await?;
            processed += 1;
        }
        Ok(processed)
    }

    async fn run_assistant_sync_skills(&self) -> Result<()> {
        let Some(assistant_id) = self.store.builtin_assistant_id().await? else {
            return Ok(());
        };
        if let Some(dir) = self.store.builtin_assistant_skills_dir().await? {
            self.store.sync_skills_from_disk(&assistant_id, &dir).await?;
        }
        let _ = self
            .enqueue_assistant_task_after(AssistantQueueTask::SyncSkills, 90)
            .await;
        Ok(())
    }

    pub async fn run_memory_maintenance(
        &self,
    ) -> Result<crate::memory_maintenance::MemoryMaintenanceReport> {
        crate::memory_maintenance::run_memory_maintenance(&self.store, &self.providers).await
    }

    async fn run_assistant_consolidate(&self) -> Result<()> {
        let report = self.run_memory_maintenance().await?;
        tracing::info!(
            expired = report.expired_deleted,
            raw_considered = report.ingest.raw_considered,
            raw_noise = report.ingest.raw_skipped_noise,
            curated_created = report.ingest.curated_created,
            raw_archived = report.ingest.raw_archived,
            ingest_parse_failed = report.ingest.llm_parse_failed,
            curated_considered = report.curated_organize.curated_considered,
            curated_updated = report.curated_organize.updated,
            curated_deleted = report.curated_organize.deleted,
            embeddings = report.embeddings_updated,
            "memory maintenance done"
        );
        let _ = self.store.reset_assistant_observe_streak().await;
        let _ = self
            .enqueue_assistant_task_after(AssistantQueueTask::ConsolidateMemory, 135)
            .await;
        Ok(())
    }

    async fn run_assistant_todo_reminder(&self, payload: Option<&str>) -> Result<()> {
        #[derive(serde::Deserialize)]
        struct ReminderPayload {
            assistant_id: String,
            title: String,
            detail: Option<String>,
            #[serde(default)]
            todo_id: Option<String>,
        }

        let Some(payload) = payload else {
            return Ok(());
        };
        let data: ReminderPayload = serde_json::from_str(payload)
            .map_err(|e| Error::bad_request(format!("invalid reminder payload: {e}")))?;
        let conv = self.store.get_or_create_dm(&data.assistant_id).await?;
        let friend = self
            .store
            .get_friend(&data.assistant_id)
            .await?
            .ok_or_else(|| Error::not_found("assistant friend"))?;
        let content = if let Some(detail) = data.detail.as_deref().filter(|d| !d.trim().is_empty()) {
            format!("提醒你：{}\n{}", data.title, detail)
        } else {
            format!("提醒你：{}", data.title)
        };
        let turn_id = uuid::Uuid::new_v4().to_string();
        let _ = self
            .store
            .insert_message(crate::store::message::NewMessage {
                conversation_id: &conv.id,
                turn_id: &turn_id,
                parent_id: None,
                sender_kind: SenderKind::Friend,
                sender_id: &friend.id,
                sender_name: &friend.name,
                content: &content,
                mentions: &[],
                status: MessageStatus::Done,
                on_behalf_of_user: false,
                workspace_id: None,
                attachments: &[],
            })
            .await?;

        if let Ok(v) = serde_json::from_str::<serde_json::Value>(payload) {
            if let Some(schedule) = v.get("schedule") {
                if schedule.get("type").and_then(|x| x.as_str()) == Some("daily_at") {
                    let hour = schedule
                        .get("hour")
                        .and_then(|x| x.as_u64())
                        .unwrap_or(9) as u32;
                    let minute = schedule
                        .get("minute")
                        .and_then(|x| x.as_u64())
                        .unwrap_or(0) as u32;
                    let timezone = schedule
                        .get("timezone")
                        .and_then(|x| x.as_str())
                        .unwrap_or("Asia/Shanghai");
                    let next_delay = next_daily_delay_seconds(hour, minute, timezone);
                    let _ = self
                        .store
                        .enqueue_assistant_job("todo_reminder", Some(payload), next_delay, 3)
                        .await;
                    if let Some(todo_id) = data.todo_id.as_deref() {
                        let next_run_at =
                            (chrono::Utc::now() + chrono::Duration::seconds(next_delay)).to_rfc3339();
                        let _ = self
                            .store
                            .update_assistant_todo_next_run(todo_id, Some(&next_run_at))
                            .await;
                        let _ = self
                            .store
                            .update_assistant_todo_status(todo_id, crate::domain::AssistantTodoStatus::Pending)
                            .await;
                    }
                }
            }
        }
        Ok(())
    }
}

fn timezone_offset_seconds(timezone: &str) -> i32 {
    match timezone {
        "UTC" | "Etc/UTC" => 0,
        _ => 8 * 3600, // 默认按 Asia/Shanghai
    }
}

fn next_daily_delay_seconds(hour: u32, minute: u32, timezone: &str) -> i64 {
    use chrono::{Datelike, Duration, TimeZone, Utc};
    let offset = chrono::FixedOffset::east_opt(timezone_offset_seconds(timezone))
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
    let delta = next.with_timezone(&Utc) - now_utc;
    delta.num_seconds().max(1)
}
