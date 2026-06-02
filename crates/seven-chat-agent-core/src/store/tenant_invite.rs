use chrono::{Duration, Utc};
use rand::distributions::Alphanumeric;
use rand::{thread_rng, Rng};
use uuid::Uuid;

use crate::domain::{TenantInvite, TenantInvitePreview};
use crate::store::SqliteStore;
use crate::{Error, Result};

#[derive(Debug, sqlx::FromRow)]
struct TenantInviteRow {
    id: String,
    tenant_id: String,
    code: String,
    invited_email: Option<String>,
    role: String,
    created_by_user_id: Option<String>,
    expires_at: String,
    used_at: Option<String>,
    used_by_user_id: Option<String>,
    created_at: String,
}

impl From<TenantInviteRow> for TenantInvite {
    fn from(r: TenantInviteRow) -> Self {
        Self {
            id: r.id,
            tenant_id: r.tenant_id,
            code: r.code,
            invited_email: r.invited_email,
            role: r.role,
            created_by_user_id: r.created_by_user_id,
            expires_at: crate::store::parse_dt(&r.expires_at),
            used_at: r.used_at.map(|s| crate::store::parse_dt(&s)),
            used_by_user_id: r.used_by_user_id,
            created_at: crate::store::parse_dt(&r.created_at),
        }
    }
}

fn normalize_invite_role(role: Option<&str>) -> Result<String> {
    let role = role.unwrap_or("member").trim().to_lowercase();
    match role.as_str() {
        "admin" | "member" => Ok(role),
        _ => Err(Error::bad_request("role 只能是 admin 或 member")),
    }
}

impl SqliteStore {
    pub async fn create_tenant_invite(
        &self,
        tenant_id: &str,
        created_by_user_id: &str,
        invited_email: Option<&str>,
        role: Option<&str>,
        expires_in_hours: i64,
    ) -> Result<TenantInvite> {
        let role = normalize_invite_role(role)?;
        let invited_email = invited_email
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(crate::auth::normalize_email)
            .transpose()?;
        let id = Uuid::new_v4().to_string();
        let code: String = thread_rng()
            .sample_iter(&Alphanumeric)
            .take(24)
            .map(char::from)
            .collect();
        let expires = Utc::now() + Duration::hours(expires_in_hours.max(1));
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "INSERT INTO tenant_invites (id, tenant_id, code, invited_email, role, created_by_user_id, expires_at, created_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(&id)
        .bind(tenant_id)
        .bind(&code)
        .bind(invited_email.as_deref())
        .bind(&role)
        .bind(created_by_user_id)
        .bind(expires.to_rfc3339())
        .bind(&now)
        .execute(self.pool())
        .await?;
        self.get_tenant_invite_by_id(&id)
            .await?
            .ok_or_else(|| Error::not_found("tenant invite after insert"))
    }

    pub async fn list_tenant_invites(&self, tenant_id: &str) -> Result<Vec<TenantInvite>> {
        let rows: Vec<TenantInviteRow> = sqlx::query_as(
            "SELECT id, tenant_id, code, invited_email, role, created_by_user_id, expires_at, used_at, used_by_user_id, created_at
             FROM tenant_invites WHERE tenant_id = ? ORDER BY created_at DESC",
        )
        .bind(tenant_id)
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(TenantInvite::from).collect())
    }

    pub async fn get_tenant_invite_by_id(&self, id: &str) -> Result<Option<TenantInvite>> {
        let row: Option<TenantInviteRow> = sqlx::query_as(
            "SELECT id, tenant_id, code, invited_email, role, created_by_user_id, expires_at, used_at, used_by_user_id, created_at
             FROM tenant_invites WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(TenantInvite::from))
    }

    pub async fn get_tenant_invite_by_code(&self, code: &str) -> Result<Option<TenantInvite>> {
        let row: Option<TenantInviteRow> = sqlx::query_as(
            "SELECT id, tenant_id, code, invited_email, role, created_by_user_id, expires_at, used_at, used_by_user_id, created_at
             FROM tenant_invites WHERE code = ?",
        )
        .bind(code.trim())
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(TenantInvite::from))
    }

    pub async fn preview_tenant_invite(&self, code: &str) -> Result<TenantInvitePreview> {
        let invite = self
            .get_tenant_invite_by_code(code)
            .await?
            .ok_or_else(|| Error::not_found("invite"))?;
        let tenant_name: String = sqlx::query_scalar("SELECT COALESCE(name, id) FROM tenants WHERE id = ?")
            .bind(&invite.tenant_id)
            .fetch_optional(self.pool())
            .await?
            .unwrap_or_else(|| invite.tenant_id.clone());
        let (valid, reason) = tenant_invite_validity(&invite, None);
        Ok(TenantInvitePreview {
            tenant_id: invite.tenant_id,
            tenant_name,
            role: invite.role,
            invited_email: invite.invited_email,
            expires_at: invite.expires_at,
            valid,
            reason,
        })
    }

    pub async fn delete_tenant_invite(&self, tenant_id: &str, id: &str) -> Result<()> {
        let r = sqlx::query("DELETE FROM tenant_invites WHERE id = ? AND tenant_id = ?")
            .bind(id)
            .bind(tenant_id)
            .execute(self.pool())
            .await?;
        if r.rows_affected() == 0 {
            return Err(Error::not_found("tenant invite"));
        }
        Ok(())
    }

    pub async fn consume_tenant_invite(
        &self,
        code: &str,
        email: &str,
        new_user_id: &str,
    ) -> Result<TenantInvite> {
        let invite = self
            .get_tenant_invite_by_code(code)
            .await?
            .ok_or_else(|| Error::bad_request("邀请码无效"))?;
        let (valid, reason) = tenant_invite_validity(&invite, Some(email));
        if !valid {
            return Err(Error::bad_request(
                reason.unwrap_or_else(|| "邀请码不可用".into()),
            ));
        }
        let now = Utc::now().to_rfc3339();
        let r = sqlx::query(
            "UPDATE tenant_invites SET used_at = ?, used_by_user_id = ? WHERE id = ? AND used_at IS NULL",
        )
        .bind(&now)
        .bind(new_user_id)
        .bind(&invite.id)
        .execute(self.pool())
        .await?;
        if r.rows_affected() == 0 {
            return Err(Error::bad_request("邀请码已被使用"));
        }
        self.get_tenant_invite_by_id(&invite.id)
            .await?
            .ok_or_else(|| Error::not_found("tenant invite after consume"))
    }

    pub async fn list_users_in_tenant(&self, tenant_id: &str) -> Result<Vec<crate::domain::UserPublic>> {
        let rows: Vec<(String, String, String, Option<String>, String, String)> = sqlx::query_as(
            "SELECT id, tenant_id, email, username, display_name, role FROM users WHERE tenant_id = ? ORDER BY created_at ASC",
        )
        .bind(tenant_id)
        .fetch_all(self.pool())
        .await?;
        Ok(rows
            .into_iter()
            .map(|(id, tenant_id, email, username, display_name, role)| {
                crate::domain::UserPublic {
                    id,
                    tenant_id,
                    email,
                    username,
                    display_name,
                    role,
                }
            })
            .collect())
    }

    pub async fn count_admins_in_tenant(&self, tenant_id: &str) -> Result<i64> {
        let n: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM users WHERE tenant_id = ? AND role = 'admin'",
        )
        .bind(tenant_id)
        .fetch_one(self.pool())
        .await?;
        Ok(n)
    }

    pub async fn update_user_role_in_tenant(
        &self,
        tenant_id: &str,
        user_id: &str,
        new_role: &str,
    ) -> Result<crate::domain::UserPublic> {
        let new_role = normalize_invite_role(Some(new_role))?;
        let current: Option<(String, String)> = sqlx::query_as(
            "SELECT id, role FROM users WHERE id = ? AND tenant_id = ?",
        )
        .bind(user_id)
        .bind(tenant_id)
        .fetch_optional(self.pool())
        .await?;
        let Some((_, current_role)) = current else {
            return Err(Error::not_found("user"));
        };
        if current_role == "admin" && new_role != "admin" {
            let admins = self.count_admins_in_tenant(tenant_id).await?;
            if admins <= 1 {
                return Err(Error::bad_request("不能移除租户内唯一管理员"));
            }
        }
        sqlx::query("UPDATE users SET role = ? WHERE id = ? AND tenant_id = ?")
            .bind(&new_role)
            .bind(user_id)
            .bind(tenant_id)
            .execute(self.pool())
            .await?;
        let user = self
            .get_user_by_id(user_id)
            .await?
            .ok_or_else(|| Error::not_found("user"))?;
        Ok(user.public())
    }
}

pub(crate) fn tenant_invite_validity(invite: &TenantInvite, email: Option<&str>) -> (bool, Option<String>) {
    if invite.used_at.is_some() {
        return (false, Some("邀请码已使用".into()));
    }
    if invite.expires_at < Utc::now() {
        return (false, Some("邀请码已过期".into()));
    }
    if let Some(expected) = invite.invited_email.as_deref() {
        if let Some(actual) = email {
            if expected != actual {
                return (false, Some("该邀请码仅限指定邮箱注册".into()));
            }
        }
    }
    (true, None)
}
