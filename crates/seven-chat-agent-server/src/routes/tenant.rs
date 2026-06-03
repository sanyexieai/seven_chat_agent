use axum::extract::{Path, State};
use axum::http::HeaderMap;
use axum::routing::{delete, get, patch, post};
use axum::{Json, Router};
use serde::Deserialize;

use crate::auth::{require_admin, session_from_request, tenant_store_from_request};
use crate::routes::errors::ApiError;
use crate::state::AppState;

pub fn tenant_router() -> Router<AppState> {
    Router::new()
        .route("/overview", get(admin_overview))
        .route("/profile", patch(update_tenant_profile))
        .route("/members", get(list_tenant_members).post(create_tenant_member))
        .route("/members/:user_id", patch(update_tenant_member).delete(delete_tenant_member))
        .route("/members/:user_id/role", patch(update_member_role))
        .route("/sessions", get(list_tenant_sessions))
        .route("/sessions/purge-expired", post(purge_expired_sessions))
        .route("/sessions/:session_id", delete(revoke_tenant_session))
        .route("/sessions/revoke-user", post(revoke_user_sessions))
        .route("/conversations", get(list_tenant_conversations))
        .route(
            "/conversations/:conversation_id",
            patch(update_tenant_conversation).delete(delete_tenant_conversation),
        )
        .route(
            "/invites",
            get(list_tenant_invites).post(create_tenant_invite),
        )
        .route(
            "/invites/:id",
            patch(update_tenant_invite).delete(delete_tenant_invite),
        )
}

async fn list_tenant_members(
    State(s): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let members = store.list_users_in_tenant(store.tenant_id()).await?;
    Ok(Json(serde_json::json!({
        "members": members,
        "tenant_id": session.tenant_id,
    })))
}

#[derive(Debug, Deserialize)]
struct UpdateMemberRoleBody {
    role: String,
}

async fn update_member_role(
    State(s): State<AppState>,
    headers: HeaderMap,
    Path(user_id): Path<String>,
    Json(body): Json<UpdateMemberRoleBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let user = store
        .update_user_role_in_tenant(store.tenant_id(), &user_id, &body.role)
        .await?;
    Ok(Json(serde_json::json!({ "user": user })))
}

#[derive(Debug, Deserialize)]
struct CreateTenantInviteBody {
    #[serde(default)]
    invited_email: Option<String>,
    #[serde(default)]
    role: Option<String>,
    #[serde(default = "default_invite_hours")]
    expires_in_hours: i64,
}

fn default_invite_hours() -> i64 {
    168
}

async fn list_tenant_invites(
    State(s): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let invites = store.list_tenant_invites(store.tenant_id()).await?;
    Ok(Json(serde_json::json!({ "invites": invites })))
}

async fn create_tenant_invite(
    State(s): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<CreateTenantInviteBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let invite = store
        .create_tenant_invite(
            store.tenant_id(),
            &session.user_id,
            body.invited_email.as_deref(),
            body.role.as_deref(),
            body.expires_in_hours,
        )
        .await?;
    Ok(Json(serde_json::json!({ "invite": invite })))
}

async fn admin_overview(
    State(s): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let overview = store
        .tenant_admin_overview(store.tenant_id())
        .await?;
    Ok(Json(serde_json::json!({ "overview": overview })))
}

async fn list_tenant_sessions(
    State(s): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let sessions = store
        .list_tenant_user_sessions(store.tenant_id(), 200)
        .await?;
    Ok(Json(serde_json::json!({ "sessions": sessions })))
}

async fn revoke_tenant_session(
    State(s): State<AppState>,
    headers: HeaderMap,
    Path(session_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    store
        .revoke_tenant_user_session(store.tenant_id(), &session_id)
        .await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

#[derive(Debug, Deserialize)]
struct RevokeUserSessionsBody {
    user_id: String,
    #[serde(default)]
    keep_current: bool,
}

async fn revoke_user_sessions(
    State(s): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<RevokeUserSessionsBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let except_session_id = if body.keep_current {
        let token = headers
            .get(axum::http::header::AUTHORIZATION)
            .and_then(|v| v.to_str().ok())
            .and_then(|h| h.strip_prefix("Bearer "))
            .map(str::trim);
        if let Some(tok) = token {
            store.find_session_id_by_token(tok).await?
        } else {
            None
        }
    } else {
        None
    };
    let revoked = store
        .revoke_all_user_sessions_in_tenant(
            store.tenant_id(),
            &body.user_id,
            except_session_id.as_deref(),
        )
        .await?;
    Ok(Json(serde_json::json!({ "ok": true, "revoked": revoked })))
}

async fn list_tenant_conversations(
    State(s): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let conversations = store
        .list_tenant_conversations_admin(store.tenant_id(), 200)
        .await?;
    Ok(Json(serde_json::json!({ "conversations": conversations })))
}

async fn delete_tenant_invite(
    State(s): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    store.delete_tenant_invite(store.tenant_id(), &id).await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

#[derive(Debug, Deserialize)]
struct UpdateTenantProfileBody {
    name: String,
    #[serde(default)]
    slug: Option<String>,
}

async fn update_tenant_profile(
    State(s): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<UpdateTenantProfileBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let tenant = store
        .update_tenant_profile(
            store.tenant_id(),
            &body.name,
            body.slug.as_deref(),
        )
        .await?;
    Ok(Json(serde_json::json!({ "tenant": tenant })))
}

#[derive(Debug, Deserialize)]
struct CreateTenantMemberBody {
    email: String,
    username: String,
    password: String,
    display_name: String,
    #[serde(default)]
    role: Option<String>,
}

async fn create_tenant_member(
    State(s): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<CreateTenantMemberBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let user = store
        .admin_create_tenant_member(
            store.tenant_id(),
            &body.email,
            &body.username,
            &body.password,
            &body.display_name,
            body.role.as_deref(),
        )
        .await?;
    Ok(Json(serde_json::json!({ "user": user })))
}

#[derive(Debug, Deserialize)]
struct UpdateTenantMemberBody {
    #[serde(default)]
    display_name: Option<String>,
    #[serde(default)]
    email: Option<String>,
    #[serde(default)]
    username: Option<String>,
    #[serde(default)]
    password: Option<String>,
    #[serde(default)]
    role: Option<String>,
}

async fn update_tenant_member(
    State(s): State<AppState>,
    headers: HeaderMap,
    Path(user_id): Path<String>,
    Json(body): Json<UpdateTenantMemberBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let user = store
        .admin_update_tenant_member(
            store.tenant_id(),
            &user_id,
            body.display_name.as_deref(),
            body.email.as_deref(),
            body.username.as_deref(),
            body.password.as_deref(),
            body.role.as_deref(),
        )
        .await?;
    Ok(Json(serde_json::json!({ "user": user })))
}

async fn delete_tenant_member(
    State(s): State<AppState>,
    headers: HeaderMap,
    Path(user_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    store
        .admin_delete_tenant_member(store.tenant_id(), &user_id, &session.user_id)
        .await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

#[derive(Debug, Deserialize)]
struct UpdateTenantInviteBody {
    #[serde(default)]
    invited_email: Option<Option<String>>,
    #[serde(default)]
    role: Option<String>,
    #[serde(default)]
    expires_in_hours: Option<i64>,
}

async fn update_tenant_invite(
    State(s): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    Json(body): Json<UpdateTenantInviteBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let invite = store
        .update_tenant_invite_admin(
            store.tenant_id(),
            &id,
            body.invited_email,
            body.role.as_deref(),
            body.expires_in_hours,
        )
        .await?;
    Ok(Json(serde_json::json!({ "invite": invite })))
}

#[derive(Debug, Deserialize)]
struct UpdateConversationBody {
    #[serde(default)]
    title: Option<String>,
}

async fn update_tenant_conversation(
    State(s): State<AppState>,
    headers: HeaderMap,
    Path(conversation_id): Path<String>,
    Json(body): Json<UpdateConversationBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let conversation = store
        .admin_update_tenant_conversation(
            store.tenant_id(),
            &conversation_id,
            body.title.as_deref(),
        )
        .await?;
    Ok(Json(serde_json::json!({ "conversation": conversation })))
}

async fn delete_tenant_conversation(
    State(s): State<AppState>,
    headers: HeaderMap,
    Path(conversation_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    store
        .admin_delete_tenant_conversation(store.tenant_id(), &conversation_id)
        .await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

async fn purge_expired_sessions(
    State(s): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = session_from_request(&s, &headers).await?;
    require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let purged = store
        .admin_purge_expired_sessions(store.tenant_id())
        .await?;
    Ok(Json(serde_json::json!({ "ok": true, "purged": purged })))
}
