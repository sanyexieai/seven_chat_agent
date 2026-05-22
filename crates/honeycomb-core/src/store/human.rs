use chrono::{Duration, Utc};
use rand::distributions::Alphanumeric;
use rand::{thread_rng, Rng};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HumanSession {
    pub friend_id: String,
    pub channel: String,
    pub endpoint: Option<String>,
    pub auth_token_ref: Option<String>,
    pub presence: String,
    pub typing_until: Option<chrono::DateTime<chrono::Utc>>,
    pub last_seen_at: Option<chrono::DateTime<chrono::Utc>>,
    pub updated_at: chrono::DateTime<chrono::Utc>,
}

#[derive(Debug, sqlx::FromRow)]
struct HumanSessionRow {
    friend_id: String,
    channel: String,
    endpoint: Option<String>,
    auth_token_ref: Option<String>,
    presence: String,
    typing_until: Option<String>,
    last_seen_at: Option<String>,
    updated_at: String,
}

impl From<HumanSessionRow> for HumanSession {
    fn from(r: HumanSessionRow) -> Self {
        Self {
            friend_id: r.friend_id,
            channel: r.channel,
            endpoint: r.endpoint,
            auth_token_ref: r.auth_token_ref,
            presence: r.presence,
            typing_until: r.typing_until.as_deref().map(parse_dt),
            last_seen_at: r.last_seen_at.as_deref().map(parse_dt),
            updated_at: parse_dt(&r.updated_at),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Invite {
    pub id: String,
    pub friend_id: String,
    pub code: String,
    pub expires_at: Option<chrono::DateTime<chrono::Utc>>,
    pub used_at: Option<chrono::DateTime<chrono::Utc>>,
    pub created_at: chrono::DateTime<chrono::Utc>,
}

#[derive(Debug, sqlx::FromRow)]
struct InviteRow {
    id: String,
    friend_id: String,
    code: String,
    expires_at: Option<String>,
    used_at: Option<String>,
    created_at: String,
}

impl From<InviteRow> for Invite {
    fn from(r: InviteRow) -> Self {
        Self {
            id: r.id,
            friend_id: r.friend_id,
            code: r.code,
            expires_at: r.expires_at.as_deref().map(parse_dt),
            used_at: r.used_at.as_deref().map(parse_dt),
            created_at: parse_dt(&r.created_at),
        }
    }
}

impl SqliteStore {
    pub async fn upsert_human_session(
        &self,
        friend_id: &str,
        channel: &str,
        endpoint: Option<&str>,
    ) -> Result<HumanSession> {
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "INSERT INTO human_sessions (friend_id, channel, endpoint, presence, last_seen_at, updated_at) VALUES (?, ?, ?, 'online', ?, ?) ON CONFLICT(friend_id) DO UPDATE SET channel = excluded.channel, endpoint = excluded.endpoint, presence = 'online', last_seen_at = excluded.last_seen_at, updated_at = excluded.updated_at",
        )
        .bind(friend_id)
        .bind(channel)
        .bind(endpoint)
        .bind(&now)
        .bind(&now)
        .execute(self.pool())
        .await?;
        self.get_human_session(friend_id)
            .await?
            .ok_or_else(|| Error::not_found("human session after upsert"))
    }

    pub async fn get_human_session(&self, friend_id: &str) -> Result<Option<HumanSession>> {
        let row: Option<HumanSessionRow> = sqlx::query_as(
            "SELECT friend_id, channel, endpoint, auth_token_ref, presence, typing_until, last_seen_at, updated_at FROM human_sessions WHERE friend_id = ?",
        )
        .bind(friend_id)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(HumanSession::from))
    }

    pub async fn set_human_typing(&self, friend_id: &str, until_ms: i64) -> Result<()> {
        let until = Utc::now() + Duration::milliseconds(until_ms);
        sqlx::query(
            "UPDATE human_sessions SET typing_until = ?, presence = 'online', updated_at = ? WHERE friend_id = ?",
        )
        .bind(until.to_rfc3339())
        .bind(Utc::now().to_rfc3339())
        .bind(friend_id)
        .execute(self.pool())
        .await?;
        Ok(())
    }

    pub async fn list_typing_humans(&self) -> Result<Vec<String>> {
        let now = Utc::now().to_rfc3339();
        let rows: Vec<(String,)> = sqlx::query_as(
            "SELECT friend_id FROM human_sessions WHERE typing_until IS NOT NULL AND typing_until > ?",
        )
        .bind(&now)
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(|(s,)| s).collect())
    }

    pub async fn create_invite(
        &self,
        friend_id: &str,
        expires_in_hours: i64,
    ) -> Result<Invite> {
        let id = Uuid::new_v4().to_string();
        let code: String = thread_rng()
            .sample_iter(&Alphanumeric)
            .take(24)
            .map(char::from)
            .collect();
        let expires = Utc::now() + Duration::hours(expires_in_hours);
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "INSERT INTO invites (id, friend_id, code, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        )
        .bind(&id)
        .bind(friend_id)
        .bind(&code)
        .bind(expires.to_rfc3339())
        .bind(&now)
        .execute(self.pool())
        .await?;
        self.get_invite_by_id(&id)
            .await?
            .ok_or_else(|| Error::not_found("invite after insert"))
    }

    pub async fn list_invites(&self, friend_id: &str) -> Result<Vec<Invite>> {
        let rows: Vec<InviteRow> = sqlx::query_as(
            "SELECT id, friend_id, code, expires_at, used_at, created_at FROM invites WHERE friend_id = ? ORDER BY created_at DESC",
        )
        .bind(friend_id)
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(Invite::from).collect())
    }

    pub async fn get_invite_by_id(&self, id: &str) -> Result<Option<Invite>> {
        let row: Option<InviteRow> = sqlx::query_as(
            "SELECT id, friend_id, code, expires_at, used_at, created_at FROM invites WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(Invite::from))
    }

    pub async fn get_invite_by_code(&self, code: &str) -> Result<Option<Invite>> {
        let row: Option<InviteRow> = sqlx::query_as(
            "SELECT id, friend_id, code, expires_at, used_at, created_at FROM invites WHERE code = ?",
        )
        .bind(code)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(Invite::from))
    }

    pub async fn consume_invite(&self, code: &str) -> Result<Invite> {
        let invite = self
            .get_invite_by_code(code)
            .await?
            .ok_or_else(|| Error::not_found("invite"))?;
        if invite.used_at.is_some() {
            return Err(Error::bad_request("invite already used"));
        }
        if let Some(exp) = invite.expires_at {
            if exp < Utc::now() {
                return Err(Error::bad_request("invite expired"));
            }
        }
        let now = Utc::now().to_rfc3339();
        sqlx::query("UPDATE invites SET used_at = ? WHERE id = ?")
            .bind(&now)
            .bind(&invite.id)
            .execute(self.pool())
            .await?;
        self.get_invite_by_id(&invite.id)
            .await?
            .ok_or_else(|| Error::not_found("invite after consume"))
    }

    pub async fn delete_invite(&self, id: &str) -> Result<()> {
        sqlx::query("DELETE FROM invites WHERE id = ?")
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }
}
