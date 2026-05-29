use chrono::{Duration, Utc};
use uuid::Uuid;

use crate::store::{parse_dt, SqliteStore};
use crate::Result;

#[derive(Debug, Clone, serde::Serialize)]
pub struct AssistantQueueJob {
    pub id: String,
    pub kind: String,
    pub payload: Option<String>,
    pub attempts: i64,
    pub max_attempts: i64,
    pub status: String,
    pub last_error: Option<String>,
    pub run_at: chrono::DateTime<Utc>,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct AssistantQueueStats {
    pub pending: i64,
    pub running: i64,
    pub done: i64,
    pub failed: i64,
    pub due_pending: i64,
}

#[derive(Debug, sqlx::FromRow)]
struct AssistantQueueJobRow {
    id: String,
    kind: String,
    payload: Option<String>,
    attempts: i64,
    max_attempts: i64,
    status: String,
    last_error: Option<String>,
    run_at: String,
}

impl From<AssistantQueueJobRow> for AssistantQueueJob {
    fn from(r: AssistantQueueJobRow) -> Self {
        Self {
            id: r.id,
            kind: r.kind,
            payload: r.payload,
            attempts: r.attempts,
            max_attempts: r.max_attempts,
            status: r.status,
            last_error: r.last_error,
            run_at: parse_dt(&r.run_at),
        }
    }
}

impl SqliteStore {
    pub async fn enqueue_assistant_job(
        &self,
        kind: &str,
        payload: Option<&str>,
        delay_seconds: i64,
        max_attempts: i64,
    ) -> Result<()> {
        let id = Uuid::new_v4().to_string();
        let now = Utc::now();
        let run_at = now + Duration::seconds(delay_seconds.max(0));
        sqlx::query(
            "INSERT INTO assistant_queue_jobs (id, kind, payload, status, attempts, max_attempts, run_at, last_error, created_at, updated_at) VALUES (?, ?, ?, 'pending', 0, ?, ?, NULL, ?, ?)",
        )
        .bind(&id)
        .bind(kind)
        .bind(payload)
        .bind(max_attempts.max(1))
        .bind(run_at.to_rfc3339())
        .bind(now.to_rfc3339())
        .bind(now.to_rfc3339())
        .execute(self.pool())
        .await?;
        Ok(())
    }

    pub async fn fetch_due_assistant_jobs(&self, limit: i64) -> Result<Vec<AssistantQueueJob>> {
        let now = Utc::now().to_rfc3339();
        let rows: Vec<AssistantQueueJobRow> = sqlx::query_as(
            "SELECT id, kind, payload, attempts, max_attempts, status, last_error, run_at FROM assistant_queue_jobs WHERE status = 'pending' AND run_at <= ? ORDER BY run_at ASC LIMIT ?",
        )
        .bind(&now)
        .bind(limit.max(1))
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(Into::into).collect())
    }

    pub async fn next_due_assistant_job_at(&self) -> Result<Option<chrono::DateTime<Utc>>> {
        let run_at: Option<String> = sqlx::query_scalar(
            "SELECT run_at FROM assistant_queue_jobs WHERE status = 'pending' ORDER BY run_at ASC LIMIT 1",
        )
        .fetch_optional(self.pool())
        .await?;
        Ok(run_at.as_deref().map(parse_dt))
    }

    pub async fn list_assistant_queue_jobs(
        &self,
        status: Option<&str>,
        limit: i64,
    ) -> Result<Vec<AssistantQueueJob>> {
        let rows: Vec<AssistantQueueJobRow> = if let Some(status) = status {
            sqlx::query_as(
                "SELECT id, kind, payload, attempts, max_attempts, status, last_error, run_at FROM assistant_queue_jobs WHERE status = ? ORDER BY run_at DESC LIMIT ?",
            )
            .bind(status)
            .bind(limit.max(1))
            .fetch_all(self.pool())
            .await?
        } else {
            sqlx::query_as(
                "SELECT id, kind, payload, attempts, max_attempts, status, last_error, run_at FROM assistant_queue_jobs ORDER BY run_at DESC LIMIT ?",
            )
            .bind(limit.max(1))
            .fetch_all(self.pool())
            .await?
        };
        Ok(rows.into_iter().map(Into::into).collect())
    }

    pub async fn assistant_queue_stats(&self) -> Result<AssistantQueueStats> {
        let pending: i64 =
            sqlx::query_scalar("SELECT COUNT(1) FROM assistant_queue_jobs WHERE status='pending'")
                .fetch_one(self.pool())
                .await?;
        let running: i64 =
            sqlx::query_scalar("SELECT COUNT(1) FROM assistant_queue_jobs WHERE status='running'")
                .fetch_one(self.pool())
                .await?;
        let done: i64 =
            sqlx::query_scalar("SELECT COUNT(1) FROM assistant_queue_jobs WHERE status='done'")
                .fetch_one(self.pool())
                .await?;
        let failed: i64 =
            sqlx::query_scalar("SELECT COUNT(1) FROM assistant_queue_jobs WHERE status='failed'")
                .fetch_one(self.pool())
                .await?;
        let now = Utc::now().to_rfc3339();
        let due_pending: i64 = sqlx::query_scalar(
            "SELECT COUNT(1) FROM assistant_queue_jobs WHERE status='pending' AND run_at <= ?",
        )
        .bind(now)
        .fetch_one(self.pool())
        .await?;
        Ok(AssistantQueueStats {
            pending,
            running,
            done,
            failed,
            due_pending,
        })
    }

    pub async fn replay_failed_assistant_jobs(&self, limit: i64) -> Result<i64> {
        let now = Utc::now().to_rfc3339();
        let result = sqlx::query(
            "UPDATE assistant_queue_jobs
             SET status='pending', attempts=0, run_at=?, last_error=NULL, updated_at=?
             WHERE id IN (
                 SELECT id FROM assistant_queue_jobs
                 WHERE status='failed'
                 ORDER BY updated_at DESC
                 LIMIT ?
             )",
        )
        .bind(&now)
        .bind(&now)
        .bind(limit.max(1))
        .execute(self.pool())
        .await?;
        Ok(result.rows_affected() as i64)
    }

    pub async fn mark_assistant_job_running(&self, id: &str) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        sqlx::query("UPDATE assistant_queue_jobs SET status = 'running', updated_at = ? WHERE id = ?")
            .bind(now)
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn mark_assistant_job_done(&self, id: &str) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        sqlx::query("UPDATE assistant_queue_jobs SET status = 'done', updated_at = ? WHERE id = ?")
            .bind(now)
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn mark_assistant_job_failed_or_retry(
        &self,
        job: &AssistantQueueJob,
        err: &str,
    ) -> Result<()> {
        let attempts = job.attempts + 1;
        let now = Utc::now();
        if attempts >= job.max_attempts {
            sqlx::query(
                "UPDATE assistant_queue_jobs SET status = 'failed', attempts = ?, last_error = ?, updated_at = ? WHERE id = ?",
            )
            .bind(attempts)
            .bind(err)
            .bind(now.to_rfc3339())
            .bind(&job.id)
            .execute(self.pool())
            .await?;
            return Ok(());
        }
        let retry_at = now + Duration::seconds(30 * attempts.max(1));
        sqlx::query(
            "UPDATE assistant_queue_jobs SET status = 'pending', attempts = ?, run_at = ?, last_error = ?, updated_at = ? WHERE id = ?",
        )
        .bind(attempts)
        .bind(retry_at.to_rfc3339())
        .bind(err)
        .bind(now.to_rfc3339())
        .bind(&job.id)
        .execute(self.pool())
        .await?;
        Ok(())
    }
}

