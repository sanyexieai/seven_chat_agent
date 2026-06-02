use axum::extract::{Path, State};
use axum::http::HeaderMap;
use axum::routing::{delete, get, patch};
use axum::{Json, Router};
use serde::Deserialize;

use crate::auth::{require_admin, session_from_request, tenant_store_from_request};
use crate::routes::errors::ApiError;
use crate::state::AppState;

pub fn tenant_router() -> Router<AppState> {
    Router::new()
        .route("/members", get(list_tenant_members))
        .route("/members/:user_id/role", patch(update_member_role))
        .route("/invites", get(list_tenant_invites).post(create_tenant_invite))
        .route("/invites/:id", delete(delete_tenant_invite))
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
