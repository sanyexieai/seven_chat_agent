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
    scope_user_id: Option<String>,
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
            scope_user_id: self.scope_user_id,
            created_at: parse_dt(&self.created_at),
        })
    }
}

const CONV_SELECT: &str =
    "id, kind, target_id, title, last_message_at, scope_user_id, created_at";

impl SqliteStore {
    fn dm_scope_sql(&self) -> &'static str {
        if self.is_user_scoped() {
            " AND scope_user_id = ?"
        } else {
            " AND scope_user_id IS NULL"
        }
    }

    fn conversation_visible_to_caller(&self, conv: &Conversation) -> bool {
        match (&self.user_id, &conv.scope_user_id, conv.kind) {
            (_, _, ConvKind::Group) => true,
            (Some(uid), Some(suid), ConvKind::Dm) => uid == suid,
            (None, None, ConvKind::Dm) => true,
            _ => false,
        }
    }

    pub async fn list_conversations(&self) -> Result<Vec<Conversation>> {
        let sql = if self.is_user_scoped() {
            format!(
                "SELECT {CONV_SELECT} FROM conversations WHERE tenant_id = ? \
                 AND (kind != 'dm' OR scope_user_id = ?) ORDER BY COALESCE(last_message_at, created_at) DESC"
            )
        } else {
            format!(
                "SELECT {CONV_SELECT} FROM conversations WHERE tenant_id = ? \
                 AND (kind != 'dm' OR scope_user_id IS NULL) ORDER BY COALESCE(last_message_at, created_at) DESC"
            )
        };
        let mut q = sqlx::query_as::<_, ConvRow>(&sql).bind(self.tenant_id());
        if let Some(uid) = self.user_id.as_deref() {
            q = q.bind(uid);
        }
        let rows = q.fetch_all(self.pool()).await?;
        rows.into_iter().map(|r| r.into_conv()).collect()
    }

    async fn fetch_conversation_row(&self, id: &str) -> Result<Option<Conversation>> {
        let row = sqlx::query_as::<_, ConvRow>(&format!(
            "SELECT {CONV_SELECT} FROM conversations WHERE id = ? AND tenant_id = ?"
        ))
        .bind(id)
        .bind(self.tenant_id())
        .fetch_optional(self.pool())
        .await?;
        row.map(|r| r.into_conv()).transpose()
    }

    pub async fn get_conversation(&self, id: &str) -> Result<Option<Conversation>> {
        let conv = self.fetch_conversation_row(id).await?;
        if let Some(ref c) = conv {
            if !self.conversation_visible_to_caller(c) {
                return Ok(None);
            }
        }
        Ok(conv)
    }

    /// 调度器内部用：不按当前请求用户过滤可见性。
    pub async fn get_conversation_internal(&self, id: &str) -> Result<Option<Conversation>> {
        self.fetch_conversation_row(id).await
    }

    pub async fn get_or_create_dm(&self, friend_id: &str) -> Result<Conversation> {
        let sql = format!(
            "SELECT {CONV_SELECT} FROM conversations WHERE kind = 'dm' AND target_id = ? AND tenant_id = ?{}",
            self.dm_scope_sql()
        );
        let mut q = sqlx::query_as::<_, ConvRow>(&sql)
            .bind(friend_id)
            .bind(self.tenant_id());
        if let Some(uid) = self.user_id.as_deref() {
            q = q.bind(uid);
        }
        if let Some(r) = q.fetch_optional(self.pool()).await? {
            return r.into_conv();
        }
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let scope_user_id = self.user_id.clone();
        sqlx::query(
            "INSERT INTO conversations (id, kind, target_id, title, last_message_at, tenant_id, scope_user_id, created_at) VALUES (?, 'dm', ?, NULL, NULL, ?, ?, ?)",
        )
        .bind(&id)
        .bind(friend_id)
        .bind(self.tenant_id())
        .bind(&scope_user_id)
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
