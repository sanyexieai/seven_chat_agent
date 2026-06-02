use chrono::{Duration, Utc};
use uuid::Uuid;

use crate::auth::{
    generate_session_token, hash_password, hash_session_token, normalize_email,
    normalize_login_account, normalize_tenant_slug, normalize_username, session_ttl_days,
    verify_password, LoginAccountKind,
};
use crate::domain::{AuthSession, User, UserPublic};
use crate::store::SqliteStore;
use crate::{Error, Result};

#[derive(Debug, serde::Deserialize)]
pub struct RegisterUser {
    pub email: String,
    pub username: String,
    pub password: String,
    pub display_name: String,
    pub tenant_slug: Option<String>,
    /// 租户邀请码；提供时忽略 tenant_slug，加入邀请所属租户。
    pub invite_code: Option<String>,
}

#[derive(Debug, serde::Deserialize)]
pub struct LoginUser {
    /// 邮箱或用户名（兼容旧字段名 `email`）
    #[serde(alias = "email", alias = "account")]
    pub login: String,
    pub password: String,
    pub tenant_slug: Option<String>,
}

#[derive(Debug, serde::Serialize)]
pub struct AuthResponse {
    pub token: String,
    pub expires_at: String,
    pub user: UserPublic,
    pub tenant_id: String,
}

const USER_SELECT: &str =
    "id, tenant_id, email, username, display_name, role, created_at";

impl SqliteStore {
    fn row_to_user(
        id: String,
        tenant_id: String,
        email: String,
        username: Option<String>,
        display_name: String,
        role: String,
        created_at: String,
    ) -> User {
        User {
            id,
            tenant_id,
            email,
            username,
            display_name,
            role,
            created_at: crate::store::parse_dt(&created_at),
        }
    }

    async fn user_exists_by_email(&self, tenant_id: &str, email: &str) -> Result<bool> {
        let id: Option<String> = sqlx::query_scalar(
            "SELECT id FROM users WHERE tenant_id = ? AND email = ?",
        )
        .bind(tenant_id)
        .bind(email)
        .fetch_optional(self.pool())
        .await?;
        Ok(id.is_some())
    }

    async fn user_exists_by_username(&self, tenant_id: &str, username: &str) -> Result<bool> {
        let id: Option<String> = sqlx::query_scalar(
            "SELECT id FROM users WHERE tenant_id = ? AND username = ?",
        )
        .bind(tenant_id)
        .bind(username)
        .fetch_optional(self.pool())
        .await?;
        Ok(id.is_some())
    }

    async fn find_user_credentials(
        &self,
        tenant_id: &str,
        account: LoginAccountKind,
    ) -> Result<Option<(String, String)>> {
        let row = match account {
            LoginAccountKind::Email(email) => {
                sqlx::query_as::<_, (String, String)>(
                    "SELECT id, password_hash FROM users WHERE tenant_id = ? AND email = ?",
                )
                .bind(tenant_id)
                .bind(&email)
                .fetch_optional(self.pool())
                .await?
            }
            LoginAccountKind::Username(username) => {
                sqlx::query_as::<_, (String, String)>(
                    "SELECT id, password_hash FROM users WHERE tenant_id = ? AND username = ?",
                )
                .bind(tenant_id)
                .bind(&username)
                .fetch_optional(self.pool())
                .await?
            }
        };
        Ok(row)
    }

    pub async fn ensure_tenant_by_slug(&self, slug: &str) -> Result<String> {
        let existing: Option<String> =
            sqlx::query_scalar("SELECT id FROM tenants WHERE slug = ? OR id = ?")
                .bind(slug)
                .bind(slug)
                .fetch_optional(self.pool())
                .await?;
        if let Some(id) = existing {
            return Ok(id);
        }
        let id = slug.to_string();
        sqlx::query(
            "INSERT INTO tenants (id, name, slug, created_at) VALUES (?, ?, ?, ?)",
        )
        .bind(&id)
        .bind(&id)
        .bind(slug)
        .bind(Utc::now().to_rfc3339())
        .execute(self.pool())
        .await?;
        sqlx::query(
            r#"INSERT OR IGNORE INTO assistant_global_settings (id, settings, updated_at)
               SELECT ?, settings, updated_at FROM assistant_global_settings WHERE id = 'global'"#,
        )
        .bind(&id)
        .execute(self.pool())
        .await?;
        let tenant_store = self.for_tenant(&id);
        crate::provider::registry::seed_default_providers(&tenant_store).await?;
        tenant_store.ensure_agent_dna().await?;
        Ok(id)
    }

    pub async fn count_users_in_tenant(&self, tenant_id: &str) -> Result<i64> {
        let n: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM users WHERE tenant_id = ?")
            .bind(tenant_id)
            .fetch_one(self.pool())
            .await?;
        Ok(n)
    }

    async fn insert_user(
        &self,
        tenant_id: &str,
        email: &str,
        username: &str,
        password_hash: &str,
        display_name: &str,
        role: &str,
    ) -> Result<String> {
        if self.user_exists_by_email(tenant_id, email).await? {
            return Err(Error::bad_request("该租户下邮箱已注册"));
        }
        if self.user_exists_by_username(tenant_id, username).await? {
            return Err(Error::bad_request("该租户下用户名已占用"));
        }
        let user_id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "INSERT INTO users (id, tenant_id, email, username, password_hash, display_name, role, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(&user_id)
        .bind(tenant_id)
        .bind(email)
        .bind(username)
        .bind(password_hash)
        .bind(display_name)
        .bind(role)
        .bind(&now)
        .execute(self.pool())
        .await?;
        Ok(user_id)
    }

    pub async fn register_user(&self, req: RegisterUser) -> Result<AuthResponse> {
        let email = normalize_email(&req.email)?;
        let username = normalize_username(&req.username)?;
        let display_name = req.display_name.trim();
        if display_name.is_empty() {
            return Err(Error::bad_request("display_name 不能为空"));
        }
        let password_hash = hash_password(&req.password)?;

        if let Some(code) = req
            .invite_code
            .as_deref()
            .map(str::trim)
            .filter(|s| !s.is_empty())
        {
            let invite = self
                .get_tenant_invite_by_code(code)
                .await?
                .ok_or_else(|| Error::bad_request("邀请码无效"))?;
            let (valid, reason) = crate::store::tenant_invite::tenant_invite_validity(
                &invite,
                Some(&email),
            );
            if !valid {
                return Err(Error::bad_request(
                    reason.unwrap_or_else(|| "邀请码不可用".into()),
                ));
            }
            let tenant_id = invite.tenant_id.clone();
            let role = invite.role.clone();
            let user_id = self
                .insert_user(
                    &tenant_id,
                    &email,
                    &username,
                    &password_hash,
                    display_name,
                    &role,
                )
                .await?;
            self.consume_tenant_invite(code, &email, &user_id).await?;
            return self.create_session_for_user(&user_id).await;
        }

        let slug = normalize_tenant_slug(req.tenant_slug.as_deref())?;
        let tenant_id = self.ensure_tenant_by_slug(&slug).await?;
        let user_count = self.count_users_in_tenant(&tenant_id).await?;
        let role = if user_count == 0 { "admin" } else { "member" };
        let user_id = self
            .insert_user(
                &tenant_id,
                &email,
                &username,
                &password_hash,
                display_name,
                role,
            )
            .await?;
        self.create_session_for_user(&user_id).await
    }

    pub async fn login_user(&self, req: LoginUser) -> Result<AuthResponse> {
        let account = normalize_login_account(&req.login)?;
        let slug = normalize_tenant_slug(req.tenant_slug.as_deref())?;
        let tenant_id = self.ensure_tenant_by_slug(&slug).await?;
        let row = self
            .find_user_credentials(&tenant_id, account)
            .await?
            .ok_or_else(|| Error::unauthorized("账号或密码错误"))?;
        let (user_id, password_hash) = row;
        if !verify_password(&req.password, &password_hash)? {
            return Err(Error::unauthorized("账号或密码错误"));
        }
        self.create_session_for_user(&user_id).await
    }

    async fn create_session_for_user(&self, user_id: &str) -> Result<AuthResponse> {
        let user = self
            .get_user_by_id(user_id)
            .await?
            .ok_or_else(|| Error::not_found("user"))?;
        let token = generate_session_token();
        let token_hash = hash_session_token(&token);
        let session_id = Uuid::new_v4().to_string();
        let expires = Utc::now() + Duration::days(session_ttl_days());
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "INSERT INTO user_sessions (id, user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        )
        .bind(&session_id)
        .bind(user_id)
        .bind(&token_hash)
        .bind(expires.to_rfc3339())
        .bind(&now)
        .execute(self.pool())
        .await?;
        Ok(AuthResponse {
            token,
            expires_at: expires.to_rfc3339(),
            user: user.public(),
            tenant_id: user.tenant_id,
        })
    }

    pub async fn logout_session(&self, token: &str) -> Result<()> {
        let token_hash = hash_session_token(token);
        sqlx::query("DELETE FROM user_sessions WHERE token_hash = ?")
            .bind(&token_hash)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn resolve_session(&self, token: &str) -> Result<Option<AuthSession>> {
        let token_hash = hash_session_token(token);
        let row: Option<(String, String, String, Option<String>, String, String, String)> =
            sqlx::query_as(
                r#"SELECT u.id, u.tenant_id, u.email, u.username, u.display_name, u.role, s.expires_at
               FROM user_sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ?"#,
            )
            .bind(&token_hash)
            .fetch_optional(self.pool())
            .await?;
        let Some((id, tenant_id, email, username, display_name, role, expires_at)) = row else {
            return Ok(None);
        };
        let exp = chrono::DateTime::parse_from_rfc3339(&expires_at)
            .map(|d| d.with_timezone(&Utc))
            .unwrap_or_else(|_| Utc::now() - Duration::seconds(1));
        if exp < Utc::now() {
            sqlx::query("DELETE FROM user_sessions WHERE token_hash = ?")
                .bind(&token_hash)
                .execute(self.pool())
                .await?;
            return Ok(None);
        }
        Ok(Some(AuthSession {
            user_id: id,
            tenant_id,
            email,
            username,
            display_name,
            role,
        }))
    }

    pub async fn get_user_by_id(&self, user_id: &str) -> Result<Option<User>> {
        let row: Option<(
            String,
            String,
            String,
            Option<String>,
            String,
            String,
            String,
        )> = sqlx::query_as(&format!(
            "SELECT {USER_SELECT} FROM users WHERE id = ?"
        ))
        .bind(user_id)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(
            |(id, tenant_id, email, username, display_name, role, created_at)| {
                Self::row_to_user(id, tenant_id, email, username, display_name, role, created_at)
            },
        ))
    }
}
