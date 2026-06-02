use axum::extract::{Path, State};
use axum::http::HeaderMap;
use axum::routing::{get, post};
use axum::{Json, Router};
use seven_chat_agent_core::store::user::{LoginUser, RegisterUser};

use crate::auth::extract_bearer_from_headers;
use crate::routes::errors::ApiError;
use crate::state::AppState;

pub fn auth_router() -> Router<AppState> {
    Router::new()
        .route("/register", post(register))
        .route("/login", post(login))
        .route("/logout", post(logout))
        .route("/me", get(me))
        .route("/status", get(status))
        .route("/invite/:code", get(preview_tenant_invite))
}

async fn register(
    State(state): State<AppState>,
    Json(body): Json<RegisterUser>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let auth = state.core.store.register_user(body).await?;
    Ok(Json(serde_json::json!({ "auth": auth })))
}

async fn login(
    State(state): State<AppState>,
    Json(body): Json<LoginUser>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let auth = state.core.store.login_user(body).await?;
    Ok(Json(serde_json::json!({ "auth": auth })))
}

async fn logout(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let token = extract_bearer_from_headers(&headers)
        .ok_or_else(|| ApiError::Unauthorized("需要 Bearer token".into()))?;
    state.core.store.logout_session(&token).await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

async fn me(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let auth = crate::auth::resolve_optional_auth(&state, &headers).await?;
    let session = auth.require()?;
    let user = state
        .core
        .store
        .get_user_by_id(&session.user_id)
        .await?
        .ok_or_else(|| ApiError::NotFound)?;
    Ok(Json(serde_json::json!({
        "user": user.public(),
        "tenant_id": session.tenant_id,
    })))
}

async fn status() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "auth_required": seven_chat_agent_core::auth::auth_required(),
    }))
}

async fn preview_tenant_invite(
    State(state): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let preview = state.core.store.preview_tenant_invite(&code).await?;
    Ok(Json(serde_json::json!({ "preview": preview })))
}
