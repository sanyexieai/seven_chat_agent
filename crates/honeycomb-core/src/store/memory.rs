use chrono::Utc;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Memory {
    pub id: String,
    pub owner_friend_id: String,
    pub kind: String,
    pub content: String,
    pub source_message_id: Option<String>,
    pub weight: f64,
    pub pinned: bool,
    pub last_used_at: Option<chrono::DateTime<chrono::Utc>>,
    pub decay_score: f64,
    pub created_at: chrono::DateTime<chrono::Utc>,
}

#[derive(Debug, sqlx::FromRow)]
struct MemoryRow {
    id: String,
    owner_friend_id: String,
    kind: String,
    content: String,
    source_message_id: Option<String>,
    weight: f64,
    pinned: i64,
    last_used_at: Option<String>,
    decay_score: f64,
    created_at: String,
}

impl From<MemoryRow> for Memory {
    fn from(r: MemoryRow) -> Self {
        Memory {
            id: r.id,
            owner_friend_id: r.owner_friend_id,
            kind: r.kind,
            content: r.content,
            source_message_id: r.source_message_id,
            weight: r.weight,
            pinned: r.pinned != 0,
            last_used_at: r.last_used_at.as_deref().map(parse_dt),
            decay_score: r.decay_score,
            created_at: parse_dt(&r.created_at),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NewMemory {
    pub owner_friend_id: String,
    pub kind: String,
    pub content: String,
    pub source_message_id: Option<String>,
    pub weight: f64,
    #[serde(default)]
    pub pinned: bool,
}

impl SqliteStore {
    pub async fn insert_memory(&self, m: NewMemory) -> Result<Memory> {
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "INSERT INTO memories (id, owner_friend_id, kind, content, source_message_id, weight, pinned, decay_score, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1.0, ?)",
        )
        .bind(&id)
        .bind(&m.owner_friend_id)
        .bind(&m.kind)
        .bind(&m.content)
        .bind(&m.source_message_id)
        .bind(m.weight)
        .bind(if m.pinned { 1 } else { 0 })
        .bind(&now)
        .execute(self.pool())
        .await?;
        self.get_memory(&id)
            .await?
            .ok_or_else(|| Error::not_found("memory after insert"))
    }

    pub async fn get_memory(&self, id: &str) -> Result<Option<Memory>> {
        let row: Option<MemoryRow> = sqlx::query_as(
            "SELECT id, owner_friend_id, kind, content, source_message_id, weight, pinned, last_used_at, decay_score, created_at FROM memories WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(Memory::from))
    }

    pub async fn list_memories(
        &self,
        owner: &str,
        kind: Option<&str>,
        limit: i64,
    ) -> Result<Vec<Memory>> {
        let rows: Vec<MemoryRow> = if let Some(k) = kind {
            sqlx::query_as(
                "SELECT id, owner_friend_id, kind, content, source_message_id, weight, pinned, last_used_at, decay_score, created_at FROM memories WHERE owner_friend_id = ? AND kind = ? ORDER BY pinned DESC, weight DESC, created_at DESC LIMIT ?",
            )
            .bind(owner)
            .bind(k)
            .bind(limit)
            .fetch_all(self.pool())
            .await?
        } else {
            sqlx::query_as(
                "SELECT id, owner_friend_id, kind, content, source_message_id, weight, pinned, last_used_at, decay_score, created_at FROM memories WHERE owner_friend_id = ? ORDER BY pinned DESC, weight DESC, created_at DESC LIMIT ?",
            )
            .bind(owner)
            .bind(limit)
            .fetch_all(self.pool())
            .await?
        };
        Ok(rows.into_iter().map(Memory::from).collect())
    }

    pub async fn search_memories(
        &self,
        owner: &str,
        query: &str,
        limit: i64,
    ) -> Result<Vec<Memory>> {
        let q = sanitize_fts(query);
        if q.is_empty() {
            return Ok(vec![]);
        }
        let rows: Vec<MemoryRow> = sqlx::query_as(
            "SELECT m.id, m.owner_friend_id, m.kind, m.content, m.source_message_id, m.weight, m.pinned, m.last_used_at, m.decay_score, m.created_at FROM memories_fts f JOIN memories m ON m.rowid = f.rowid WHERE memories_fts MATCH ? AND m.owner_friend_id = ? ORDER BY m.pinned DESC, m.weight DESC, m.created_at DESC LIMIT ?",
        )
        .bind(&q)
        .bind(owner)
        .bind(limit)
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(Memory::from).collect())
    }

    pub async fn touch_memory(&self, id: &str) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        sqlx::query("UPDATE memories SET last_used_at = ?, decay_score = MIN(1.0, decay_score + 0.05) WHERE id = ?")
            .bind(&now)
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn delete_memory(&self, id: &str) -> Result<()> {
        sqlx::query("DELETE FROM memories WHERE id = ?")
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn pin_memory(&self, id: &str, pinned: bool) -> Result<()> {
        sqlx::query("UPDATE memories SET pinned = ? WHERE id = ?")
            .bind(if pinned { 1 } else { 0 })
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn consolidate_memories(&self, owner: &str) -> Result<()> {
        sqlx::query(
            "UPDATE memories SET decay_score = decay_score * 0.95 WHERE owner_friend_id = ? AND pinned = 0",
        )
        .bind(owner)
        .execute(self.pool())
        .await?;
        sqlx::query(
            "DELETE FROM memories WHERE owner_friend_id = ? AND pinned = 0 AND decay_score < 0.1",
        )
        .bind(owner)
        .execute(self.pool())
        .await?;
        Ok(())
    }
}

fn sanitize_fts(s: &str) -> String {
    let cleaned: String = s
        .chars()
        .map(|c| if c.is_alphanumeric() || c == ' ' { c } else { ' ' })
        .collect();
    let tokens: Vec<&str> = cleaned.split_whitespace().take(8).collect();
    if tokens.is_empty() {
        return String::new();
    }
    tokens
        .iter()
        .map(|t| format!("\"{t}\""))
        .collect::<Vec<_>>()
        .join(" OR ")
}
