use chrono::Utc;
use uuid::Uuid;

use crate::domain::{ConvKind, Conversation};
use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

#[derive(Debug, sqlx::FromRow)]
struct ConvRow {
    id: String,
    kind: String,
    target_id: String,
    title: Option<String>,
    last_message_at: Option<String>,
    created_at: String,
}

impl ConvRow {
    fn into_conv(self) -> Result<Conversation> {
        let kind = match self.kind.as_str() {
            "dm" => ConvKind::Dm,
            "group" => ConvKind::Group,
            other => return Err(Error::Config(format!("unknown conv kind {other}"))),
        };
        Ok(Conversation {
            id: self.id,
            kind,
            target_id: self.target_id,
            title: self.title,
            last_message_at: self.last_message_at.as_deref().map(parse_dt),
            created_at: parse_dt(&self.created_at),
        })
    }
}

impl SqliteStore {
    pub async fn list_conversations(&self) -> Result<Vec<Conversation>> {
        let rows = sqlx::query_as::<_, ConvRow>(
            "SELECT id, kind, target_id, title, last_message_at, created_at FROM conversations ORDER BY COALESCE(last_message_at, created_at) DESC",
        )
        .fetch_all(self.pool())
        .await?;
        rows.into_iter().map(|r| r.into_conv()).collect()
    }

    pub async fn get_conversation(&self, id: &str) -> Result<Option<Conversation>> {
        let row = sqlx::query_as::<_, ConvRow>(
            "SELECT id, kind, target_id, title, last_message_at, created_at FROM conversations WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(self.pool())
        .await?;
        row.map(|r| r.into_conv()).transpose()
    }

    pub async fn get_or_create_dm(&self, friend_id: &str) -> Result<Conversation> {
        let row = sqlx::query_as::<_, ConvRow>(
            "SELECT id, kind, target_id, title, last_message_at, created_at FROM conversations WHERE kind = 'dm' AND target_id = ?",
        )
        .bind(friend_id)
        .fetch_optional(self.pool())
        .await?;
        if let Some(r) = row {
            return r.into_conv();
        }
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "INSERT INTO conversations (id, kind, target_id, title, last_message_at, created_at) VALUES (?, 'dm', ?, NULL, NULL, ?)",
        )
        .bind(&id)
        .bind(friend_id)
        .bind(&now)
        .execute(self.pool())
        .await?;
        self.get_conversation(&id)
            .await?
            .ok_or_else(|| Error::not_found("conversation after insert"))
    }

    pub async fn touch_conversation(&self, id: &str) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        sqlx::query("UPDATE conversations SET last_message_at = ? WHERE id = ?")
            .bind(&now)
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }
}
