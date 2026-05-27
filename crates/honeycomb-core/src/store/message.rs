use chrono::Utc;
use uuid::Uuid;

use crate::domain::{CliBlock, Message, MessageStatus, SenderKind};
use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

#[derive(Debug, sqlx::FromRow)]
struct MessageRow {
    id: String,
    conversation_id: String,
    turn_id: String,
    parent_id: Option<String>,
    sender_kind: String,
    sender_id: String,
    sender_name: String,
    content: String,
    content_blocks: Option<String>,
    mentions: String,
    status: String,
    seen_by: String,
    model_used: Option<String>,
    tokens_in: Option<i64>,
    tokens_out: Option<i64>,
    created_at: String,
}

impl MessageRow {
    fn into_message(self) -> Result<Message> {
        let sender_kind = SenderKind::parse(&self.sender_kind)
            .ok_or_else(|| Error::Config(format!("unknown sender_kind {}", self.sender_kind)))?;
        let status = MessageStatus::parse(&self.status)
            .ok_or_else(|| Error::Config(format!("unknown status {}", self.status)))?;
        let mentions: Vec<String> = serde_json::from_str(&self.mentions).unwrap_or_default();
        let seen_by: Vec<String> = serde_json::from_str(&self.seen_by).unwrap_or_default();
        Ok(Message {
            id: self.id,
            conversation_id: self.conversation_id,
            turn_id: self.turn_id,
            parent_id: self.parent_id,
            sender_kind,
            sender_id: self.sender_id,
            sender_name: self.sender_name,
            content: self.content,
            content_blocks: self
                .content_blocks
                .as_deref()
                .and_then(worker_bee_cli::parse_cli_blocks_json),
            mentions,
            status,
            seen_by,
            model_used: self.model_used,
            tokens_in: self.tokens_in,
            tokens_out: self.tokens_out,
            created_at: parse_dt(&self.created_at),
        })
    }
}

#[derive(Debug)]
pub struct NewMessage<'a> {
    pub conversation_id: &'a str,
    pub turn_id: &'a str,
    pub parent_id: Option<&'a str>,
    pub sender_kind: SenderKind,
    pub sender_id: &'a str,
    pub sender_name: &'a str,
    pub content: &'a str,
    pub mentions: &'a [String],
    pub status: MessageStatus,
}

impl SqliteStore {
    pub async fn insert_message(&self, m: NewMessage<'_>) -> Result<Message> {
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let mentions = serde_json::to_string(m.mentions)?;
        sqlx::query(
            r#"INSERT INTO messages
                (id, conversation_id, turn_id, parent_id, sender_kind, sender_id, sender_name, content, mentions, status, seen_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?)"#,
        )
        .bind(&id)
        .bind(m.conversation_id)
        .bind(m.turn_id)
        .bind(m.parent_id)
        .bind(m.sender_kind.as_str())
        .bind(m.sender_id)
        .bind(m.sender_name)
        .bind(m.content)
        .bind(&mentions)
        .bind(m.status.as_str())
        .bind(&now)
        .execute(self.pool())
        .await?;
        self.touch_conversation(m.conversation_id).await?;
        self.get_message(&id)
            .await?
            .ok_or_else(|| Error::not_found("message after insert"))
    }

    pub async fn update_message_content(
        &self,
        id: &str,
        content: &str,
        status: MessageStatus,
    ) -> Result<()> {
        sqlx::query("UPDATE messages SET content = ?, status = ? WHERE id = ?")
            .bind(content)
            .bind(status.as_str())
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn update_message_status(&self, id: &str, status: MessageStatus) -> Result<()> {
        sqlx::query("UPDATE messages SET status = ? WHERE id = ?")
            .bind(status.as_str())
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn finalize_message(
        &self,
        id: &str,
        content: &str,
        status: MessageStatus,
        model_used: Option<&str>,
        tokens_in: Option<i64>,
        tokens_out: Option<i64>,
        content_blocks: Option<&[CliBlock]>,
    ) -> Result<()> {
        let blocks_json = content_blocks
            .filter(|b| !b.is_empty())
            .map(serde_json::to_string)
            .transpose()?;
        sqlx::query(
            "UPDATE messages SET content = ?, content_blocks = ?, status = ?, model_used = ?, tokens_in = ?, tokens_out = ? WHERE id = ?",
        )
        .bind(content)
        .bind(blocks_json)
        .bind(status.as_str())
        .bind(model_used)
        .bind(tokens_in)
        .bind(tokens_out)
        .bind(id)
        .execute(self.pool())
        .await?;
        Ok(())
    }

    pub async fn get_message(&self, id: &str) -> Result<Option<Message>> {
        let row = sqlx::query_as::<_, MessageRow>(
            "SELECT id, conversation_id, turn_id, parent_id, sender_kind, sender_id, sender_name, content, content_blocks, mentions, status, seen_by, model_used, tokens_in, tokens_out, created_at FROM messages WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(self.pool())
        .await?;
        row.map(|r| r.into_message()).transpose()
    }

    pub async fn list_messages(
        &self,
        conversation_id: &str,
        limit: i64,
    ) -> Result<Vec<Message>> {
        let rows = sqlx::query_as::<_, MessageRow>(
            "SELECT id, conversation_id, turn_id, parent_id, sender_kind, sender_id, sender_name, content, content_blocks, mentions, status, seen_by, model_used, tokens_in, tokens_out, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?",
        )
        .bind(conversation_id)
        .bind(limit)
        .fetch_all(self.pool())
        .await?;
        rows.into_iter().map(|r| r.into_message()).collect()
    }

    pub async fn recent_messages(
        &self,
        conversation_id: &str,
        limit: i64,
    ) -> Result<Vec<Message>> {
        let rows = sqlx::query_as::<_, MessageRow>(
            "SELECT * FROM (SELECT id, conversation_id, turn_id, parent_id, sender_kind, sender_id, sender_name, content, content_blocks, mentions, status, seen_by, model_used, tokens_in, tokens_out, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?) ORDER BY created_at ASC",
        )
        .bind(conversation_id)
        .bind(limit)
        .fetch_all(self.pool())
        .await?;
        rows.into_iter().map(|r| r.into_message()).collect()
    }

    pub async fn search_messages(&self, query: &str, limit: i64) -> Result<Vec<Message>> {
        let rows = sqlx::query_as::<_, MessageRow>(
            "SELECT m.id, m.conversation_id, m.turn_id, m.parent_id, m.sender_kind, m.sender_id, m.sender_name, m.content, m.content_blocks, m.mentions, m.status, m.seen_by, m.model_used, m.tokens_in, m.tokens_out, m.created_at FROM messages_fts f JOIN messages m ON m.rowid = f.rowid WHERE messages_fts MATCH ? ORDER BY m.created_at DESC LIMIT ?",
        )
        .bind(query)
        .bind(limit)
        .fetch_all(self.pool())
        .await?;
        rows.into_iter().map(|r| r.into_message()).collect()
    }
}
