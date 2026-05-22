use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::routing::{delete, get, post};
use axum::{Json, Router};
use honeycomb_core::domain::{Provider, ProviderCapabilities, ProviderPrice};
use honeycomb_core::store::friend::UpsertFriend;
use honeycomb_core::store::group::UpsertGroup;
use honeycomb_core::store::memory::NewMemory;
use honeycomb_core::store::provider::UpsertProviderKey;
use serde::Deserialize;

use crate::state::AppState;

pub mod errors;

use errors::ApiError;

pub fn api_router() -> Router<AppState> {
    Router::new()
        .route("/health", get(health))
        .route("/friends", get(list_friends).post(upsert_friend))
        .route("/friends/:id", get(get_friend).delete(delete_friend))
        .route("/groups", get(list_groups).post(upsert_group))
        .route("/groups/:id", get(get_group))
        .route("/providers", get(list_providers).post(upsert_provider))
        .route("/providers/:id", delete(delete_provider))
        .route("/provider_keys", get(list_provider_keys).post(upsert_provider_key))
        .route("/provider_keys/:id", delete(delete_provider_key))
        .route("/conversations", get(list_conversations))
        .route("/conversations/:id", get(get_conversation))
        .route("/conversations/:id/messages", get(list_messages))
        .route(
            "/conversations/dm/:friend_id",
            get(open_dm).post(send_message),
        )
        .route("/conversations/:id/send", post(send_to_conversation))
        .route("/assistant/:friend_id/memories", get(list_memories).post(add_memory))
        .route("/assistant/:friend_id/memories/:memory_id", delete(delete_memory))
        .route("/assistant/:friend_id/skills", get(list_skills))
        .route("/assistant/:friend_id/reflections", get(list_reflections))
        .route("/invites", get(list_all_invites).post(create_invite))
        .route("/invites/:id", delete(delete_invite))
        .route("/human/:code/state", get(human_state))
        .route("/human/:code/send", post(human_send))
        .route("/human/:code/typing", post(human_typing))
}

async fn health() -> impl IntoResponse {
    (StatusCode::OK, Json(serde_json::json!({"ok": true})))
}

async fn list_friends(State(s): State<AppState>) -> Result<Json<serde_json::Value>, ApiError> {
    let friends = s.core.store.list_friends().await?;
    Ok(Json(serde_json::json!({ "friends": friends })))
}

async fn get_friend(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let f = s
        .core
        .store
        .get_friend(&id)
        .await?
        .ok_or_else(|| ApiError::NotFound)?;
    Ok(Json(serde_json::json!({ "friend": f })))
}

async fn upsert_friend(
    State(s): State<AppState>,
    Json(req): Json<UpsertFriend>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let f = s.core.store.upsert_friend(req).await?;
    s.core.agents.invalidate(&f.id);
    Ok(Json(serde_json::json!({ "friend": f })))
}

async fn delete_friend(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    s.core.store.delete_friend(&id).await?;
    s.core.agents.invalidate(&id);
    Ok(Json(serde_json::json!({ "ok": true })))
}

async fn list_groups(State(s): State<AppState>) -> Result<Json<serde_json::Value>, ApiError> {
    let groups = s.core.store.list_groups().await?;
    let mut out = Vec::new();
    for g in &groups {
        out.push(group_bundle_json(&s.core.store, g).await?);
    }
    Ok(Json(serde_json::json!({ "groups": out })))
}

async fn get_group(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let g = s
        .core
        .store
        .get_group(&id)
        .await?
        .ok_or_else(|| ApiError::NotFound)?;
    let mut bundle = group_bundle_json(&s.core.store, &g).await?;
    let conv = s.core.store.get_or_create_group_conversation(&g.id).await?;
    bundle["conversation_id"] = serde_json::json!(conv.id);
    Ok(Json(bundle))
}

async fn upsert_group(
    State(s): State<AppState>,
    Json(req): Json<UpsertGroup>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let g = s.core.store.upsert_group(req).await?;
    let mut bundle = group_bundle_json(&s.core.store, &g).await?;
    let conv = s.core.store.get_or_create_group_conversation(&g.id).await?;
    bundle["conversation_id"] = serde_json::json!(conv.id);
    Ok(Json(bundle))
}

async fn group_bundle_json(
    store: &honeycomb_core::store::SqliteStore,
    g: &honeycomb_core::domain::Group,
) -> Result<serde_json::Value, ApiError> {
    let members = store.list_group_member_configs(&g.id).await?;
    let member_ids: Vec<String> = members.iter().map(|m| m.friend_id.clone()).collect();
    Ok(serde_json::json!({
        "group": g,
        "member_ids": member_ids,
        "members": members,
    }))
}

async fn list_providers(State(s): State<AppState>) -> Result<Json<serde_json::Value>, ApiError> {
    let providers = s.core.store.list_providers().await?;
    Ok(Json(serde_json::json!({ "providers": providers })))
}

#[derive(Debug, Deserialize)]
struct UpsertProviderReq {
    id: String,
    kind: String,
    display_name: String,
    base_url: String,
    #[serde(default)]
    default_model: Option<String>,
    #[serde(default)]
    capabilities: Option<ProviderCapabilities>,
    #[serde(default)]
    price: Option<ProviderPrice>,
    #[serde(default = "default_true")]
    enabled: bool,
}

fn default_true() -> bool {
    true
}

async fn upsert_provider(
    State(s): State<AppState>,
    Json(req): Json<UpsertProviderReq>,
) -> Result<Json<serde_json::Value>, ApiError> {
    if req.id.trim().is_empty() {
        return Err(ApiError::BadRequest("provider id is required".into()));
    }
    // 保留原 created_at，没有就用 now
    let created_at = match s.core.store.get_provider(&req.id).await? {
        Some(existing) => existing.created_at,
        None => chrono::Utc::now(),
    };
    let provider = Provider {
        id: req.id,
        kind: req.kind,
        display_name: req.display_name,
        base_url: req.base_url,
        default_model: req.default_model,
        capabilities: req.capabilities.unwrap_or_default(),
        price: req.price.unwrap_or_default(),
        enabled: req.enabled,
        created_at,
    };
    s.core.store.upsert_provider(&provider).await?;
    s.core.providers.reload().await?;
    Ok(Json(serde_json::json!({ "provider": provider })))
}

async fn delete_provider(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    s.core.store.delete_provider(&id).await?;
    s.core.providers.reload().await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

#[derive(Debug, Deserialize)]
struct ProviderKeyQuery {
    provider_id: Option<String>,
}

async fn list_provider_keys(
    State(s): State<AppState>,
    axum::extract::Query(q): axum::extract::Query<ProviderKeyQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let keys = s.core.store.list_provider_keys(q.provider_id.as_deref()).await?;
    Ok(Json(serde_json::json!({ "provider_keys": keys })))
}

async fn upsert_provider_key(
    State(s): State<AppState>,
    Json(req): Json<UpsertProviderKey>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let k = s.core.store.upsert_provider_key(req).await?;
    s.core.providers.reload().await?;
    Ok(Json(serde_json::json!({ "provider_key": k })))
}

async fn delete_provider_key(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    s.core.store.delete_provider_key(&id).await?;
    s.core.providers.reload().await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

async fn list_conversations(
    State(s): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let convs = s.core.store.list_conversations().await?;
    Ok(Json(serde_json::json!({ "conversations": convs })))
}

async fn get_conversation(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let c = s
        .core
        .store
        .get_conversation(&id)
        .await?
        .ok_or_else(|| ApiError::NotFound)?;
    Ok(Json(serde_json::json!({ "conversation": c })))
}

async fn list_messages(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let messages = s.core.store.list_messages(&id, 500).await?;
    Ok(Json(serde_json::json!({ "messages": messages })))
}

async fn open_dm(
    State(s): State<AppState>,
    Path(friend_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let conv = s.core.store.get_or_create_dm(&friend_id).await?;
    let messages = s.core.store.list_messages(&conv.id, 200).await?;
    Ok(Json(serde_json::json!({
        "conversation": conv,
        "messages": messages,
    })))
}

#[derive(Debug, Deserialize)]
struct SendBody {
    content: String,
}

async fn send_message(
    State(s): State<AppState>,
    Path(friend_id): Path<String>,
    Json(body): Json<SendBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let conv = s.core.store.get_or_create_dm(&friend_id).await?;
    let core = s.core.clone();
    let conv_id = conv.id.clone();
    let content = body.content.clone();
    tokio::spawn(async move {
        if let Err(e) = core.dispatcher.send_user_message(&conv_id, &content).await {
            tracing::error!(err = %e, "send_user_message failed");
        }
    });
    Ok(Json(serde_json::json!({ "ok": true, "conversation_id": conv.id })))
}

async fn send_to_conversation(
    State(s): State<AppState>,
    Path(id): Path<String>,
    Json(body): Json<SendBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let core = s.core.clone();
    let conv_id = id.clone();
    let content = body.content.clone();
    tokio::spawn(async move {
        if let Err(e) = core.dispatcher.send_user_message(&conv_id, &content).await {
            tracing::error!(err = %e, "send_user_message failed");
        }
    });
    Ok(Json(serde_json::json!({ "ok": true, "conversation_id": id })))
}

#[derive(Debug, Deserialize)]
struct MemoryQuery {
    kind: Option<String>,
    limit: Option<i64>,
}

async fn list_memories(
    State(s): State<AppState>,
    Path(friend_id): Path<String>,
    axum::extract::Query(q): axum::extract::Query<MemoryQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let memories = s
        .core
        .store
        .list_memories(&friend_id, q.kind.as_deref(), q.limit.unwrap_or(100))
        .await?;
    Ok(Json(serde_json::json!({ "memories": memories })))
}

async fn add_memory(
    State(s): State<AppState>,
    Path(friend_id): Path<String>,
    Json(mut body): Json<NewMemory>,
) -> Result<Json<serde_json::Value>, ApiError> {
    body.owner_friend_id = friend_id;
    let m = s.core.store.insert_memory(body).await?;
    Ok(Json(serde_json::json!({ "memory": m })))
}

async fn delete_memory(
    State(s): State<AppState>,
    Path((_friend_id, memory_id)): Path<(String, String)>,
) -> Result<Json<serde_json::Value>, ApiError> {
    s.core.store.delete_memory(&memory_id).await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

async fn list_skills(
    State(s): State<AppState>,
    Path(friend_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let skills = s.core.store.list_skills(&friend_id).await?;
    Ok(Json(serde_json::json!({ "skills": skills })))
}

async fn list_reflections(
    State(s): State<AppState>,
    Path(friend_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let reflections = s.core.store.list_reflections(&friend_id, 50).await?;
    Ok(Json(serde_json::json!({ "reflections": reflections })))
}

#[derive(Debug, Deserialize)]
struct CreateInviteBody {
    friend_id: String,
    #[serde(default = "default_expires")]
    expires_in_hours: i64,
}
fn default_expires() -> i64 {
    72
}

async fn create_invite(
    State(s): State<AppState>,
    Json(body): Json<CreateInviteBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let invite = s
        .core
        .store
        .create_invite(&body.friend_id, body.expires_in_hours)
        .await?;
    Ok(Json(serde_json::json!({ "invite": invite })))
}

async fn list_all_invites(
    State(s): State<AppState>,
    axum::extract::Query(q): axum::extract::Query<InviteQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    if let Some(fid) = q.friend_id {
        let invites = s.core.store.list_invites(&fid).await?;
        return Ok(Json(serde_json::json!({ "invites": invites })));
    }
    let friends = s.core.store.list_friends().await?;
    let mut all = Vec::new();
    for f in friends {
        if f.backend_kind == honeycomb_core::domain::BackendKind::Human {
            let invites = s.core.store.list_invites(&f.id).await?;
            all.extend(invites);
        }
    }
    Ok(Json(serde_json::json!({ "invites": all })))
}

#[derive(Debug, Deserialize)]
struct InviteQuery {
    friend_id: Option<String>,
}

async fn delete_invite(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    s.core.store.delete_invite(&id).await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

async fn human_state(
    State(s): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let invite = match s.core.store.get_invite_by_code(&code).await? {
        Some(i) => i,
        None => return Err(ApiError::NotFound),
    };
    if invite.used_at.is_none() {
        let _ = s.core.store.consume_invite(&code).await;
    }
    let friend = s
        .core
        .store
        .get_friend(&invite.friend_id)
        .await?
        .ok_or(ApiError::NotFound)?;
    let session = s
        .core
        .store
        .upsert_human_session(&friend.id, "invite", None)
        .await?;
    let convs = s.core.store.list_conversations().await?;
    let messages = if let Some(c) = convs.iter().find(|c| c.target_id == friend.id) {
        s.core.store.list_messages(&c.id, 200).await?
    } else {
        Vec::new()
    };
    Ok(Json(serde_json::json!({
        "friend": friend,
        "session": session,
        "messages": messages,
    })))
}

#[derive(Debug, Deserialize)]
struct HumanSendBody {
    content: String,
    conversation_id: Option<String>,
}

async fn human_send(
    State(s): State<AppState>,
    Path(code): Path<String>,
    Json(body): Json<HumanSendBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let invite = s
        .core
        .store
        .get_invite_by_code(&code)
        .await?
        .ok_or(ApiError::NotFound)?;
    let friend_id = invite.friend_id.clone();
    let conv_id = match body.conversation_id {
        Some(id) => id,
        None => {
            s.core
                .store
                .get_or_create_dm(&friend_id)
                .await?
                .id
        }
    };
    let core = s.core.clone();
    let conv_id_clone = conv_id.clone();
    let friend_id_clone = friend_id.clone();
    let content = body.content.clone();
    tokio::spawn(async move {
        if let Err(e) = core
            .dispatcher
            .send_human_message(&conv_id_clone, &friend_id_clone, &content)
            .await
        {
            tracing::error!(err = %e, "human send failed");
        }
    });
    Ok(Json(serde_json::json!({ "ok": true, "conversation_id": conv_id })))
}

#[derive(Debug, Deserialize)]
struct HumanTypingBody {
    duration_ms: Option<i64>,
}

async fn human_typing(
    State(s): State<AppState>,
    Path(code): Path<String>,
    Json(body): Json<HumanTypingBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let invite = s
        .core
        .store
        .get_invite_by_code(&code)
        .await?
        .ok_or(ApiError::NotFound)?;
    let dur = body.duration_ms.unwrap_or(3000);
    s.core
        .store
        .set_human_typing(&invite.friend_id, dur)
        .await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}
