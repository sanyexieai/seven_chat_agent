use axum::http::{header, HeaderMap, StatusCode};
use seven_chat_agent_core::auth::auth_required;
use seven_chat_agent_core::domain::AuthSession;
use seven_chat_agent_core::store::SqliteStore;

use crate::routes::errors::ApiError;
use crate::state::AppState;

/// 解析 Bearer token；`AUTH_REQUIRED=1` 且无有效 token 时返回 401。
pub struct OptionalAuth(pub Option<AuthSession>);

impl OptionalAuth {
    pub fn tenant_store(&self, state: &AppState) -> SqliteStore {
        if let Some(session) = &self.0 {
            state
                .core
                .store
                .for_tenant(&session.tenant_id)
                .for_user(&session.user_id)
        } else {
            state.core.store.as_ref().clone()
        }
    }

    pub fn session(&self) -> Option<&AuthSession> {
        self.0.as_ref()
    }

    pub fn require(&self) -> Result<&AuthSession, ApiError> {
        self.0
            .as_ref()
            .ok_or_else(|| ApiError::Unauthorized("需要登录".into()))
    }
}

pub async fn resolve_optional_auth(
    state: &AppState,
    headers: &HeaderMap,
) -> Result<OptionalAuth, ApiError> {
    if let Some(token) = extract_bearer_from_headers(headers) {
        let session = state.core.store.resolve_session(&token).await?;
        return Ok(OptionalAuth(session));
    }
    if auth_required() {
        return Err(ApiError::Unauthorized(
            "需要 Authorization: Bearer token".into(),
        ));
    }
    Ok(OptionalAuth(None))
}

/// 从请求解析 tenant 作用域 store（与 ws-api 一致）。
pub async fn tenant_store_from_request(
    state: &AppState,
    headers: &HeaderMap,
) -> Result<SqliteStore, ApiError> {
    let auth = resolve_optional_auth(state, headers).await?;
    Ok(auth.tenant_store(state))
}

pub fn extract_bearer_from_headers(headers: &HeaderMap) -> Option<String> {
    headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.strip_prefix("Bearer "))
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
}

pub fn require_admin(session: &AuthSession) -> Result<(), ApiError> {
    if session.role != "admin" {
        return Err(ApiError::Forbidden("需要管理员权限".into()));
    }
    Ok(())
}

pub async fn session_from_request(
    state: &AppState,
    headers: &HeaderMap,
) -> Result<AuthSession, ApiError> {
    let auth = resolve_optional_auth(state, headers).await?;
    Ok(auth.require()?.clone())
}

pub fn unauthorized_status() -> StatusCode {
    StatusCode::UNAUTHORIZED
}
