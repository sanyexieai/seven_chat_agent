use crate::assistant_intent::AssistantIntent;

/// 任务规划层：根据结构化意图产出可执行动作。
#[derive(Debug, Clone)]
pub enum PlannedTaskAction {
    CreateTodo {
        title: String,
        detail: Option<String>,
        repeat_rule: Option<String>,
        next_run_at: Option<String>,
        priority: i64,
    },
    EnqueueReminder {
        assistant_id: String,
        title: String,
        detail: Option<String>,
        schedule: ReminderSchedule,
    },
}

#[derive(Debug, Clone)]
pub enum ReminderSchedule {
    AfterSeconds(i64),
    DailyAt {
        hour: u32,
        minute: u32,
        timezone: String,
    },
}

#[derive(Debug, Clone)]
pub struct AssistantTaskPlan {
    pub intent: AssistantIntent,
    pub actions: Vec<PlannedTaskAction>,
}

pub fn plan_from_intent(assistant_id: &str, intent: AssistantIntent) -> AssistantTaskPlan {
    let mut actions = Vec::new();
    match &intent {
        AssistantIntent::TodoCreate {
            title,
            detail,
            priority,
            remind_after_seconds,
        } => {
            actions.push(PlannedTaskAction::CreateTodo {
                title: title.clone(),
                detail: detail.clone(),
                repeat_rule: None,
                next_run_at: None,
                priority: *priority,
            });
            if let Some(delay) = remind_after_seconds.filter(|d| *d > 0) {
                actions.push(PlannedTaskAction::EnqueueReminder {
                    assistant_id: assistant_id.to_string(),
                    title: title.clone(),
                    detail: detail.clone(),
                    schedule: ReminderSchedule::AfterSeconds(delay),
                });
            }
        }
        AssistantIntent::ReminderAfter {
            title,
            detail,
            after_seconds,
        } => {
            actions.push(PlannedTaskAction::CreateTodo {
                title: title.clone(),
                detail: detail.clone(),
                repeat_rule: None,
                next_run_at: None,
                priority: 2,
            });
            actions.push(PlannedTaskAction::EnqueueReminder {
                assistant_id: assistant_id.to_string(),
                title: title.clone(),
                detail: detail.clone(),
                schedule: ReminderSchedule::AfterSeconds((*after_seconds).max(1)),
            });
        }
        AssistantIntent::ReminderDailyAt {
            title,
            detail,
            hour,
            minute,
            timezone,
        } => {
            let next_run_at =
                next_daily_run_at_rfc3339(*hour, *minute, timezone).or_else(|| None);
            actions.push(PlannedTaskAction::CreateTodo {
                title: title.clone(),
                detail: detail.clone(),
                repeat_rule: Some(format!("daily {:02}:{:02} {}", hour, minute, timezone)),
                next_run_at,
                priority: 3,
            });
            actions.push(PlannedTaskAction::EnqueueReminder {
                assistant_id: assistant_id.to_string(),
                title: title.clone(),
                detail: detail.clone(),
                schedule: ReminderSchedule::DailyAt {
                    hour: *hour,
                    minute: *minute,
                    timezone: timezone.clone(),
                },
            });
        }
    }
    AssistantTaskPlan { intent, actions }
}

fn next_daily_run_at_rfc3339(hour: u32, minute: u32, timezone: &str) -> Option<String> {
    use chrono::{Datelike, Duration, TimeZone, Utc};
    let offset = match timezone {
        "UTC" | "Etc/UTC" => chrono::FixedOffset::east_opt(0)?,
        _ => chrono::FixedOffset::east_opt(8 * 3600)?,
    };
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
        .single()?;
    if next <= now_local {
        next += Duration::days(1);
    }
    Some(next.with_timezone(&Utc).to_rfc3339())
}
