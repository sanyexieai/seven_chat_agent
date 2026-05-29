use chrono::Utc;
use uuid::Uuid;

use crate::domain::{AssistantTodo, AssistantTodoStatus};
use crate::store::{parse_dt, SqliteStore};
use crate::Result;

#[derive(Debug, sqlx::FromRow)]
struct AssistantTodoRow {
    id: String,
    owner_friend_id: String,
    title: String,
    detail: Option<String>,
    repeat_rule: Option<String>,
    next_run_at: Option<String>,
    status: String,
    priority: i64,
    source_turn_id: Option<String>,
    created_at: String,
    updated_at: String,
}

impl From<AssistantTodoRow> for AssistantTodo {
    fn from(r: AssistantTodoRow) -> Self {
        Self {
            id: r.id,
            owner_friend_id: r.owner_friend_id,
            title: r.title,
            detail: r.detail,
            repeat_rule: r.repeat_rule,
            next_run_at: r.next_run_at.as_deref().map(parse_dt),
            status: AssistantTodoStatus::parse(&r.status),
            priority: r.priority,
            source_turn_id: r.source_turn_id,
            created_at: parse_dt(&r.created_at),
            updated_at: parse_dt(&r.updated_at),
        }
    }
}

impl SqliteStore {
    pub async fn create_assistant_todo(
        &self,
        owner_friend_id: &str,
        title: &str,
        detail: Option<&str>,
        repeat_rule: Option<&str>,
        next_run_at: Option<&str>,
        priority: i64,
        source_turn_id: Option<&str>,
    ) -> Result<AssistantTodo> {
        let now = Utc::now().to_rfc3339();
        let id = Uuid::new_v4().to_string();
        sqlx::query(
            "INSERT INTO assistant_todos (id, owner_friend_id, title, detail, repeat_rule, next_run_at, status, priority, source_turn_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)",
        )
        .bind(&id)
        .bind(owner_friend_id)
        .bind(title)
        .bind(detail)
        .bind(repeat_rule)
        .bind(next_run_at)
        .bind(priority)
        .bind(source_turn_id)
        .bind(&now)
        .bind(&now)
        .execute(self.pool())
        .await?;
        Ok(self
            .get_assistant_todo(&id)
            .await?
            .expect("assistant todo exists"))
    }

    pub async fn list_assistant_todos(
        &self,
        owner_friend_id: &str,
        status: Option<AssistantTodoStatus>,
        limit: i64,
    ) -> Result<Vec<AssistantTodo>> {
        let rows: Vec<AssistantTodoRow> = if let Some(status) = status {
            sqlx::query_as(
                "SELECT id, owner_friend_id, title, detail, repeat_rule, next_run_at, status, priority, source_turn_id, created_at, updated_at FROM assistant_todos WHERE owner_friend_id = ? AND status = ? ORDER BY priority DESC, updated_at ASC LIMIT ?",
            )
            .bind(owner_friend_id)
            .bind(status.as_str())
            .bind(limit)
            .fetch_all(self.pool())
            .await?
        } else {
            sqlx::query_as(
                "SELECT id, owner_friend_id, title, detail, repeat_rule, next_run_at, status, priority, source_turn_id, created_at, updated_at FROM assistant_todos WHERE owner_friend_id = ? ORDER BY priority DESC, updated_at ASC LIMIT ?",
            )
            .bind(owner_friend_id)
            .bind(limit)
            .fetch_all(self.pool())
            .await?
        };
        Ok(rows.into_iter().map(Into::into).collect())
    }

    pub async fn update_assistant_todo_status(
        &self,
        id: &str,
        status: AssistantTodoStatus,
    ) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        sqlx::query("UPDATE assistant_todos SET status = ?, updated_at = ? WHERE id = ?")
            .bind(status.as_str())
            .bind(&now)
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn update_assistant_todo(
        &self,
        id: &str,
        title: &str,
        detail: Option<&str>,
        priority: i64,
        status: Option<AssistantTodoStatus>,
    ) -> Result<Option<AssistantTodo>> {
        let now = Utc::now().to_rfc3339();
        if let Some(status) = status {
            sqlx::query(
                "UPDATE assistant_todos SET title = ?, detail = ?, priority = ?, status = ?, updated_at = ? WHERE id = ?",
            )
            .bind(title)
            .bind(detail)
            .bind(priority)
            .bind(status.as_str())
            .bind(&now)
            .bind(id)
            .execute(self.pool())
            .await?;
        } else {
            sqlx::query(
                "UPDATE assistant_todos SET title = ?, detail = ?, priority = ?, updated_at = ? WHERE id = ?",
            )
            .bind(title)
            .bind(detail)
            .bind(priority)
            .bind(&now)
            .bind(id)
            .execute(self.pool())
            .await?;
        }
        self.get_assistant_todo(id).await
    }

    async fn get_assistant_todo(&self, id: &str) -> Result<Option<AssistantTodo>> {
        let row: Option<AssistantTodoRow> = sqlx::query_as(
            "SELECT id, owner_friend_id, title, detail, repeat_rule, next_run_at, status, priority, source_turn_id, created_at, updated_at FROM assistant_todos WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(Into::into))
    }

    pub async fn update_assistant_todo_next_run(
        &self,
        id: &str,
        next_run_at: Option<&str>,
    ) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        sqlx::query("UPDATE assistant_todos SET next_run_at = ?, updated_at = ? WHERE id = ?")
            .bind(next_run_at)
            .bind(&now)
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    /// 修复历史数据：周期任务应保持 pending，并尽量补齐 next_run_at。
    pub async fn repair_recurring_todos(&self) -> Result<i64> {
        let now = Utc::now().to_rfc3339();
        let rows: Vec<(String, Option<String>, Option<String>, String)> = sqlx::query_as(
            "SELECT id, repeat_rule, next_run_at, status FROM assistant_todos WHERE repeat_rule IS NOT NULL",
        )
        .fetch_all(self.pool())
        .await?;
        let mut touched = 0i64;
        for (id, repeat_rule, next_run_at, status) in rows {
            let mut next_run = next_run_at;
            if next_run.is_none() {
                next_run = repeat_rule
                    .as_deref()
                    .and_then(next_run_from_repeat_rule);
            }
            let target_status = if status == "done" || status == "failed" {
                "pending"
            } else {
                status.as_str()
            };
            sqlx::query(
                "UPDATE assistant_todos SET status = ?, next_run_at = ?, updated_at = ? WHERE id = ?",
            )
            .bind(target_status)
            .bind(next_run)
            .bind(&now)
            .bind(&id)
            .execute(self.pool())
            .await?;
            touched += 1;
        }
        Ok(touched)
    }
}

fn next_run_from_repeat_rule(rule: &str) -> Option<String> {
    // 约定格式：daily HH:MM TZ
    let mut it = rule.split_whitespace();
    let kind = it.next()?;
    if kind != "daily" {
        return None;
    }
    let hm = it.next()?;
    let tz = it.next().unwrap_or("Asia/Shanghai");
    let mut hm_it = hm.split(':');
    let hour = hm_it.next()?.parse::<u32>().ok()?.min(23);
    let minute = hm_it.next()?.parse::<u32>().ok()?.min(59);

    use chrono::{Datelike, Duration, TimeZone, Utc};
    let offset = match tz {
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
            hour,
            minute,
            0,
        )
        .single()?;
    if next <= now_local {
        next += Duration::days(1);
    }
    Some(next.with_timezone(&Utc).to_rfc3339())
}

