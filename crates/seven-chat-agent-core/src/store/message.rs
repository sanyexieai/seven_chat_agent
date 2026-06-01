use chrono::Utc;
use uuid::Uuid;

use crate::domain::{CliBlock, Message, MessageStatus, SenderKind};

fn strip_delegate_confirm_prefix(s: &str) -> String {
    let t = s.trim();
    for prefix in ["【待你确认】", "【待确认】"] {
        if let Some(rest) = t.strip_prefix(prefix) {
            return rest.trim_start().to_string();
        }
    }
    t.to_string()
}
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
    on_behalf_of: i64,
    workspace_id: Option<String>,
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
            on_behalf_of_user: self.on_behalf_of != 0,
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
            workspace_id: self.workspace_id,
            created_at: parse_dt(&self.created_at),
        })
    }
}

const MESSAGE_SELECT: &str = "id, conversation_id, turn_id, parent_id, sender_kind, sender_id, sender_name, content, content_blocks, mentions, status, seen_by, model_used, tokens_in, tokens_out, on_behalf_of, workspace_id, created_at";

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
    pub on_behalf_of_user: bool,
    pub workspace_id: Option<&'a str>,
}

impl SqliteStore {
    pub async fn insert_message(&self, m: NewMessage<'_>) -> Result<Message> {
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let mentions = serde_json::to_string(m.mentions)?;
        let workspace_id = if let Some(w) = m.workspace_id.filter(|s| !s.is_empty()) {
            Some(w.to_string())
        } else {
            self.workspace_id_for_dm_conversation(m.conversation_id)
                .await?
        };
        sqlx::query(
            r#"INSERT INTO messages
                (id, conversation_id, turn_id, parent_id, sender_kind, sender_id, sender_name, content, mentions, status, seen_by, on_behalf_of, workspace_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?)"#,
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
        .bind(if m.on_behalf_of_user { 1 } else { 0 })
        .bind(&workspace_id)
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

    /// 用户确认或驳回助理「待你确认」草稿。
    pub async fn resolve_delegate_message(
        &self,
        id: &str,
        approve: bool,
        content_override: Option<&str>,
    ) -> Result<Message> {
        let msg = self
            .get_message(id)
            .await?
            .ok_or_else(|| Error::not_found("message"))?;
        if msg.status != MessageStatus::WaitingHuman {
            return Err(Error::bad_request("该消息不在待确认状态"));
        }
        if msg.sender_kind != SenderKind::Friend {
            return Err(Error::bad_request("仅助理草稿可确认"));
        }

        let mut content = content_override
            .map(str::to_string)
            .unwrap_or_else(|| msg.content.clone());
        content = strip_delegate_confirm_prefix(&content);

        let on_behalf = if approve { 1 } else { 0 };
        if !approve && !content.contains("用户未采纳") {
            content.push_str("\n\n（用户未采纳此建议）");
        }

        sqlx::query(
            "UPDATE messages SET content = ?, status = ?, on_behalf_of = ? WHERE id = ?",
        )
        .bind(&content)
        .bind(MessageStatus::Done.as_str())
        .bind(on_behalf)
        .bind(id)
        .execute(self.pool())
        .await?;

        self.get_message(id)
            .await?
            .ok_or_else(|| Error::not_found("message after resolve"))
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
        let row = sqlx::query_as::<_, MessageRow>(&format!(
            "SELECT {MESSAGE_SELECT} FROM messages WHERE id = ?"
        ))
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
        let rows = sqlx::query_as::<_, MessageRow>(&format!(
            "SELECT {MESSAGE_SELECT} FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?"
        ))
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
        let rows = sqlx::query_as::<_, MessageRow>(&format!(
            "SELECT * FROM (SELECT {MESSAGE_SELECT} FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?) ORDER BY created_at ASC"
        ))
        .bind(conversation_id)
        .bind(limit)
        .fetch_all(self.pool())
        .await?;
        rows.into_iter().map(|r| r.into_message()).collect()
    }

    pub async fn search_messages(&self, query: &str, limit: i64) -> Result<Vec<Message>> {
        let rows = sqlx::query_as::<_, MessageRow>(
            "SELECT m.id, m.conversation_id, m.turn_id, m.parent_id, m.sender_kind, m.sender_id, m.sender_name, m.content, m.content_blocks, m.mentions, m.status, m.seen_by, m.model_used, m.tokens_in, m.tokens_out, m.on_behalf_of, m.workspace_id, m.created_at FROM messages_fts f JOIN messages m ON m.rowid = f.rowid WHERE messages_fts MATCH ? ORDER BY m.created_at DESC LIMIT ?",
        )
        .bind(query)
        .bind(limit)
        .fetch_all(self.pool())
        .await?;
        rows.into_iter().map(|r| r.into_message()).collect()
    }
}
