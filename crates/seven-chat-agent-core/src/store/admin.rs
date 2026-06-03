//! 租户管理员：用户、登录会话、聊天会话等全局（租户内）视图。

use chrono::{Duration, Utc};

use crate::auth::{hash_password, hash_session_token, normalize_email, normalize_username};
use crate::domain::{
    AdminConversationSummary, AdminUserSession, TenantAdminOverview, TenantInfo, UserPublic,
};
use crate::store::tenant_invite::normalize_invite_role;
use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

impl SqliteStore {
    pub async fn get_tenant_info(&self, tenant_id: &str) -> Result<Option<TenantInfo>> {
        let row: Option<(String, String, Option<String>, String)> = sqlx::query_as(
            "SELECT id, name, slug, created_at FROM tenants WHERE id = ?",
        )
        .bind(tenant_id)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(|(id, name, slug, created_at)| TenantInfo {
            id,
            name,
            slug,
            created_at: parse_dt(&created_at),
        }))
    }

    pub async fn tenant_admin_overview(&self, tenant_id: &str) -> Result<TenantAdminOverview> {
        let info = self
            .get_tenant_info(tenant_id)
            .await?
            .ok_or_else(|| Error::not_found("tenant"))?;
        let user_count = self.count_users_in_tenant(tenant_id).await?;
        let admin_count = self.count_admins_in_tenant(tenant_id).await?;
        let now = Utc::now().to_rfc3339();
        let active_session_count: i64 = sqlx::query_scalar(
            r#"SELECT COUNT(*) FROM user_sessions s
               JOIN users u ON u.id = s.user_id
               WHERE u.tenant_id = ? AND s.expires_at > ?"#,
        )
        .bind(tenant_id)
        .bind(&now)
        .fetch_one(self.pool())
        .await?;
        let conversation_count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM conversations WHERE tenant_id = ?",
        )
        .bind(tenant_id)
        .fetch_one(self.pool())
        .await?;
        let pending_invite_count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM tenant_invites WHERE tenant_id = ? AND used_at IS NULL AND expires_at > ?",
        )
        .bind(tenant_id)
        .bind(&now)
        .fetch_one(self.pool())
        .await?;
        Ok(TenantAdminOverview {
            tenant_id: info.id,
            tenant_name: info.name,
            tenant_slug: info.slug,
            user_count,
            admin_count,
            active_session_count,
            conversation_count,
            pending_invite_count,
        })
    }

    pub async fn list_tenant_user_sessions(
        &self,
        tenant_id: &str,
        limit: i64,
    ) -> Result<Vec<AdminUserSession>> {
        let limit = limit.clamp(1, 500);
        let now = Utc::now();
        let rows: Vec<(
            String,
            String,
            String,
            String,
            Option<String>,
            String,
            String,
        )> = sqlx::query_as(
            r#"SELECT s.id, s.user_id, u.email, u.display_name, u.username, s.expires_at, s.created_at
               FROM user_sessions s
               JOIN users u ON u.id = s.user_id
               WHERE u.tenant_id = ?
               ORDER BY s.created_at DESC
               LIMIT ?"#,
        )
        .bind(tenant_id)
        .bind(limit)
        .fetch_all(self.pool())
        .await?;
        Ok(rows
            .into_iter()
            .map(
                |(id, user_id, email, display_name, username, expires_at, created_at)| {
                    let exp = chrono::DateTime::parse_from_rfc3339(&expires_at)
                        .map(|d| d.with_timezone(&Utc))
                        .unwrap_or_else(|_| Utc::now() - chrono::Duration::seconds(1));
                    AdminUserSession {
                        id,
                        user_id,
                        user_email: email,
                        user_display_name: display_name,
                        user_username: username,
                        expires_at: parse_dt(&expires_at),
                        created_at: parse_dt(&created_at),
                        is_expired: exp < now,
                    }
                },
            )
            .collect())
    }

    pub async fn revoke_tenant_user_session(
        &self,
        tenant_id: &str,
        session_id: &str,
    ) -> Result<()> {
        let r = sqlx::query(
            r#"DELETE FROM user_sessions
               WHERE id = ? AND user_id IN (SELECT id FROM users WHERE tenant_id = ?)"#,
        )
        .bind(session_id)
        .bind(tenant_id)
        .execute(self.pool())
        .await?;
        if r.rows_affected() == 0 {
            return Err(Error::not_found("session"));
        }
        Ok(())
    }

    pub async fn find_session_id_by_token(&self, token: &str) -> Result<Option<String>> {
        let token_hash = hash_session_token(token);
        let id: Option<String> =
            sqlx::query_scalar("SELECT id FROM user_sessions WHERE token_hash = ?")
                .bind(&token_hash)
                .fetch_optional(self.pool())
                .await?;
        Ok(id)
    }

    pub async fn revoke_all_user_sessions_in_tenant(
        &self,
        tenant_id: &str,
        user_id: &str,
        except_session_id: Option<&str>,
    ) -> Result<u64> {
        let user_tenant: Option<String> =
            sqlx::query_scalar("SELECT tenant_id FROM users WHERE id = ?")
                .bind(user_id)
                .fetch_optional(self.pool())
                .await?;
        if user_tenant.as_deref() != Some(tenant_id) {
            return Err(Error::not_found("user"));
        }
        let r = if let Some(sid) = except_session_id.filter(|s| !s.is_empty()) {
            sqlx::query(
                r#"DELETE FROM user_sessions
                   WHERE user_id = ? AND id != ?"#,
            )
            .bind(user_id)
            .bind(sid)
            .execute(self.pool())
            .await?
        } else {
            sqlx::query("DELETE FROM user_sessions WHERE user_id = ?")
                .bind(user_id)
                .execute(self.pool())
                .await?
        };
        Ok(r.rows_affected())
    }

    pub async fn list_tenant_conversations_admin(
        &self,
        tenant_id: &str,
        limit: i64,
    ) -> Result<Vec<AdminConversationSummary>> {
        let limit = limit.clamp(1, 500);
        let rows: Vec<(
            String,
            String,
            String,
            Option<String>,
            Option<String>,
            Option<String>,
            String,
            i64,
        )> = sqlx::query_as(
            r#"SELECT c.id, c.kind, c.target_id, c.title, c.scope_user_id, c.last_message_at, c.created_at,
                      (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
               FROM conversations c
               WHERE c.tenant_id = ?
               ORDER BY COALESCE(c.last_message_at, c.created_at) DESC
               LIMIT ?"#,
        )
        .bind(tenant_id)
        .bind(limit)
        .fetch_all(self.pool())
        .await?;
        Ok(rows
            .into_iter()
            .map(
                |(
                    id,
                    kind,
                    target_id,
                    title,
                    scope_user_id,
                    last_message_at,
                    created_at,
                    message_count,
                )| AdminConversationSummary {
                    id,
                    kind,
                    target_id,
                    title,
                    scope_user_id,
                    last_message_at: last_message_at.as_deref().map(parse_dt),
                    created_at: parse_dt(&created_at),
                    message_count,
                },
            )
            .collect())
    }

    pub async fn admin_create_tenant_member(
        &self,
        tenant_id: &str,
        email: &str,
        username: &str,
        password: &str,
        display_name: &str,
        role: Option<&str>,
    ) -> Result<UserPublic> {
        let email = normalize_email(email)?;
        let username = normalize_username(username)?;
        let display_name = display_name.trim();
        if display_name.is_empty() {
            return Err(Error::bad_request("display_name 不能为空"));
        }
        let role = normalize_invite_role(role)?;
        let password_hash = hash_password(password)?;
        let user_id = self
            .insert_user(
                tenant_id,
                &email,
                &username,
                &password_hash,
                display_name,
                &role,
            )
            .await?;
        let user = self
            .get_user_by_id(&user_id)
            .await?
            .ok_or_else(|| Error::not_found("user"))?;
        Ok(user.public())
    }

    pub async fn admin_update_tenant_member(
        &self,
        tenant_id: &str,
        user_id: &str,
        display_name: Option<&str>,
        email: Option<&str>,
        username: Option<&str>,
        password: Option<&str>,
        role: Option<&str>,
    ) -> Result<UserPublic> {
        let current = self
            .get_user_by_id(user_id)
            .await?
            .ok_or_else(|| Error::not_found("user"))?;
        if current.tenant_id != tenant_id {
            return Err(Error::not_found("user"));
        }
        let mut new_display = current.display_name.clone();
        if let Some(d) = display_name {
            let d = d.trim();
            if d.is_empty() {
                return Err(Error::bad_request("display_name 不能为空"));
            }
            new_display = d.to_string();
        }
        let mut new_email = current.email.clone();
        if let Some(e) = email {
            new_email = normalize_email(e)?;
            if self.user_exists_by_email(tenant_id, &new_email).await?
                && new_email != current.email
            {
                return Err(Error::bad_request("该租户下邮箱已注册"));
            }
        }
        let mut new_username = current.username.clone();
        if let Some(u) = username {
            let u = normalize_username(u)?;
            if self.user_exists_by_username(tenant_id, &u).await?
                && Some(u.clone()) != current.username
            {
                return Err(Error::bad_request("该租户下用户名已占用"));
            }
            new_username = Some(u);
        }
        let password_hash = if let Some(p) = password {
            if p.trim().is_empty() {
                None
            } else {
                Some(hash_password(p)?)
            }
        } else {
            None
        };
        if let Some(ref ph) = password_hash {
            sqlx::query("UPDATE users SET password_hash = ? WHERE id = ? AND tenant_id = ?")
                .bind(ph)
                .bind(user_id)
                .bind(tenant_id)
                .execute(self.pool())
                .await?;
        }
        sqlx::query(
            "UPDATE users SET display_name = ?, email = ?, username = ? WHERE id = ? AND tenant_id = ?",
        )
        .bind(&new_display)
        .bind(&new_email)
        .bind(new_username.as_deref())
        .bind(user_id)
        .bind(tenant_id)
        .execute(self.pool())
        .await?;
        if let Some(role) = role {
            return self
                .update_user_role_in_tenant(tenant_id, user_id, role)
                .await;
        }
        let user = self
            .get_user_by_id(user_id)
            .await?
            .ok_or_else(|| Error::not_found("user"))?;
        Ok(user.public())
    }

    pub async fn admin_delete_tenant_member(
        &self,
        tenant_id: &str,
        user_id: &str,
        actor_user_id: &str,
    ) -> Result<()> {
        if user_id == actor_user_id {
            return Err(Error::bad_request("不能删除当前登录账号"));
        }
        let current: Option<(String,)> = sqlx::query_as(
            "SELECT role FROM users WHERE id = ? AND tenant_id = ?",
        )
        .bind(user_id)
        .bind(tenant_id)
        .fetch_optional(self.pool())
        .await?;
        let Some((role,)) = current else {
            return Err(Error::not_found("user"));
        };
        if role == "admin" {
            let admins = self.count_admins_in_tenant(tenant_id).await?;
            if admins <= 1 {
                return Err(Error::bad_request("不能删除租户内唯一管理员"));
            }
        }
        let r = sqlx::query("DELETE FROM users WHERE id = ? AND tenant_id = ?")
            .bind(user_id)
            .bind(tenant_id)
            .execute(self.pool())
            .await?;
        if r.rows_affected() == 0 {
            return Err(Error::not_found("user"));
        }
        Ok(())
    }

    pub async fn update_tenant_invite_admin(
        &self,
        tenant_id: &str,
        invite_id: &str,
        invited_email: Option<Option<String>>,
        role: Option<&str>,
        expires_in_hours: Option<i64>,
    ) -> Result<crate::domain::TenantInvite> {
        let invite = self
            .get_tenant_invite_by_id(invite_id)
            .await?
            .ok_or_else(|| Error::not_found("tenant invite"))?;
        if invite.tenant_id != tenant_id {
            return Err(Error::not_found("tenant invite"));
        }
        if invite.used_at.is_some() {
            return Err(Error::bad_request("已使用的邀请不可修改"));
        }
        let role = match role {
            Some(r) => normalize_invite_role(Some(r))?,
            None => invite.role.clone(),
        };
        let invited_email = match invited_email {
            None => invite.invited_email.clone(),
            Some(None) => None,
            Some(Some(raw)) => {
                let raw = raw.trim();
                if raw.is_empty() {
                    None
                } else {
                    Some(normalize_email(raw)?)
                }
            }
        };
        let expires_at = if let Some(h) = expires_in_hours {
            (Utc::now() + Duration::hours(h.max(1))).to_rfc3339()
        } else {
            invite.expires_at.to_rfc3339()
        };
        sqlx::query(
            "UPDATE tenant_invites SET invited_email = ?, role = ?, expires_at = ? WHERE id = ? AND tenant_id = ?",
        )
        .bind(invited_email.as_deref())
        .bind(&role)
        .bind(&expires_at)
        .bind(invite_id)
        .bind(tenant_id)
        .execute(self.pool())
        .await?;
        self.get_tenant_invite_by_id(invite_id)
            .await?
            .ok_or_else(|| Error::not_found("tenant invite"))
    }

    pub async fn admin_delete_tenant_conversation(
        &self,
        tenant_id: &str,
        conversation_id: &str,
    ) -> Result<()> {
        let r = sqlx::query("DELETE FROM conversations WHERE id = ? AND tenant_id = ?")
            .bind(conversation_id)
            .bind(tenant_id)
            .execute(self.pool())
            .await?;
        if r.rows_affected() == 0 {
            return Err(Error::not_found("conversation"));
        }
        Ok(())
    }

    pub async fn admin_update_tenant_conversation(
        &self,
        tenant_id: &str,
        conversation_id: &str,
        title: Option<&str>,
    ) -> Result<AdminConversationSummary> {
        let title = title.map(str::trim);
        sqlx::query("UPDATE conversations SET title = ? WHERE id = ? AND tenant_id = ?")
            .bind(title)
            .bind(conversation_id)
            .bind(tenant_id)
            .execute(self.pool())
            .await?;
        let rows = self
            .list_tenant_conversations_admin(tenant_id, 500)
            .await?;
        rows.into_iter()
            .find(|c| c.id == conversation_id)
            .ok_or_else(|| Error::not_found("conversation"))
    }

    pub async fn update_tenant_profile(
        &self,
        tenant_id: &str,
        name: &str,
        slug: Option<&str>,
    ) -> Result<TenantInfo> {
        let name = name.trim();
        if name.is_empty() {
            return Err(Error::bad_request("租户名称不能为空"));
        }
        let slug = match slug.map(str::trim).filter(|s| !s.is_empty()) {
            None => None,
            Some(s) => Some(crate::auth::normalize_tenant_slug(Some(s))?),
        };
        if let Some(ref s) = slug {
            let taken: Option<String> = sqlx::query_scalar(
                "SELECT id FROM tenants WHERE slug = ? AND id != ?",
            )
            .bind(s)
            .bind(tenant_id)
            .fetch_optional(self.pool())
            .await?;
            if taken.is_some() {
                return Err(Error::bad_request("slug 已被占用"));
            }
            sqlx::query("UPDATE tenants SET name = ?, slug = ? WHERE id = ?")
                .bind(name)
                .bind(s)
                .bind(tenant_id)
                .execute(self.pool())
                .await?;
        } else {
            sqlx::query("UPDATE tenants SET name = ? WHERE id = ?")
                .bind(name)
                .bind(tenant_id)
                .execute(self.pool())
                .await?;
        }
        self.get_tenant_info(tenant_id)
            .await?
            .ok_or_else(|| Error::not_found("tenant"))
    }

    pub async fn admin_purge_expired_sessions(&self, tenant_id: &str) -> Result<u64> {
        let now = Utc::now().to_rfc3339();
        let r = sqlx::query(
            r#"DELETE FROM user_sessions
               WHERE expires_at <= ?
                 AND user_id IN (SELECT id FROM users WHERE tenant_id = ?)"#,
        )
        .bind(&now)
        .bind(tenant_id)
        .execute(self.pool())
        .await?;
        Ok(r.rows_affected())
    }
}
