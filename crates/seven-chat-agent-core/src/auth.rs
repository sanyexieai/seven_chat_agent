//! 密码哈希与会话 token。

use argon2::{
    password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString},
    Argon2,
};
use rand::rngs::OsRng;
use sha2::{Digest, Sha256};

use crate::{Error, Result};

pub fn hash_password(password: &str) -> Result<String> {
    if password.len() < 8 {
        return Err(Error::bad_request("密码至少 8 位"));
    }
    let salt = SaltString::generate(&mut OsRng);
    let argon2 = Argon2::default();
    let hash = argon2
        .hash_password(password.as_bytes(), &salt)
        .map_err(|e| Error::bad_request(format!("hash password: {e}")))?;
    Ok(hash.to_string())
}

pub fn verify_password(password: &str, password_hash: &str) -> Result<bool> {
    let parsed = PasswordHash::new(password_hash)
        .map_err(|e| Error::bad_request(format!("invalid password hash: {e}")))?;
    Ok(Argon2::default()
        .verify_password(password.as_bytes(), &parsed)
        .is_ok())
}

pub fn generate_session_token() -> String {
    format!("sess_{}", uuid::Uuid::new_v4().simple())
}

pub fn hash_session_token(token: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(token.as_bytes());
    format!("{:x}", hasher.finalize())
}

pub fn normalize_email(email: &str) -> Result<String> {
    let e = email.trim().to_lowercase();
    if !e.contains('@') || e.len() < 5 {
        return Err(Error::bad_request("邮箱格式无效"));
    }
    Ok(e)
}

/// 租户内登录用户名：2~32 位，小写字母数字与下划线，须以字母开头。
pub fn normalize_username(username: &str) -> Result<String> {
    let u = username.trim().to_lowercase();
    if u.len() < 2 || u.len() > 32 {
        return Err(Error::bad_request("用户名长度须 2~32"));
    }
    let Some(first) = u.chars().next() else {
        return Err(Error::bad_request("用户名格式无效"));
    };
    if !first.is_ascii_alphabetic() {
        return Err(Error::bad_request("用户名须以字母开头"));
    }
    if !u
        .chars()
        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
    {
        return Err(Error::bad_request("用户名仅允许小写字母、数字与下划线"));
    }
    Ok(u)
}

/// 登录标识：含 `@` 按邮箱，否则按用户名。
pub fn normalize_login_account(account: &str) -> Result<LoginAccountKind> {
    let s = account.trim();
    if s.is_empty() {
        return Err(Error::bad_request("请输入邮箱或用户名"));
    }
    if s.contains('@') {
        Ok(LoginAccountKind::Email(normalize_email(s)?))
    } else {
        Ok(LoginAccountKind::Username(normalize_username(s)?))
    }
}

#[derive(Debug, Clone)]
pub enum LoginAccountKind {
    Email(String),
    Username(String),
}

pub fn normalize_tenant_slug(slug: Option<&str>) -> Result<String> {
    let s = slug.unwrap_or("default").trim().to_lowercase();
    if s.is_empty() {
        return Ok("default".into());
    }
    if s == "default" {
        return Ok(s);
    }
    if s.len() < 2 || s.len() > 32 {
        return Err(Error::bad_request("tenant_slug 长度须 2~32"));
    }
    if !s
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '-')
    {
        return Err(Error::bad_request("tenant_slug 仅允许字母数字与连字符"));
    }
    Ok(s)
}

pub fn auth_required() -> bool {
    if let Ok(v) = std::env::var("SEVEN_CHAT_AGENT_AUTH_REQUIRED") {
        let v = v.trim().to_lowercase();
        if !v.is_empty() {
            return matches!(v.as_str(), "1" | "true" | "yes" | "on");
        }
    }
    // Release 构建默认强制登录；debug 构建保持向后兼容。
    !cfg!(debug_assertions)
}

pub fn session_ttl_days() -> i64 {
    std::env::var("SEVEN_CHAT_AGENT_SESSION_TTL_DAYS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(30)
        .clamp(1, 365)
}
