use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::routing::{delete, get, patch, post};
use axum::{Json, Router};
use seven_chat_agent_core::domain::{
    AssistantGlobalSettings, AssistantTodoStatus, Provider, ProviderCapabilities, ProviderPrice,
};
use seven_chat_agent_core::assistant_intent::{AssistantIntent, parse_quick_intent};
use seven_chat_agent_core::assistant_task_planner::plan_from_intent;
use seven_chat_agent_core::store::friend::UpsertFriend;
use seven_chat_agent_core::group_validate::{
    expert_member_ids_from_upsert, validate_group_task_flow_readiness,
};
use seven_chat_agent_core::store::group::UpsertGroup;
use seven_chat_agent_core::AssistantQueueTask;
use seven_chat_agent_core::store::memory::NewMemory;
use seven_chat_agent_core::store::workspace::{CreateWorkspace, UpdateWorkspace};
use seven_chat_agent_core::store::provider::UpsertProviderKey;
use serde::Deserialize;

use crate::auth::tenant_store_from_request;
use crate::state::AppState;

pub mod attachments;
pub mod auth;
pub mod errors;
pub mod tenant;

use errors::ApiError;

pub fn api_router() -> Router<AppState> {
    Router::new()
        .nest("/auth", auth::auth_router())
        .nest("/tenant", tenant::tenant_router())
        .route("/health", get(health))
        .route("/friends", get(list_friends).post(upsert_friend))
        .route("/friends/:id", get(get_friend).delete(delete_friend))
        .route("/friends/:id/cli_auth", get(friend_cli_auth))
        .route("/friends/:id/cli_auth/oauth/start", post(friend_cli_oauth_start))
        .route("/friends/:id/cli_auth/oauth/cancel", post(friend_cli_oauth_cancel))
        .route("/friends/:id/cli_auth/logout", post(friend_cli_logout))
        .route("/friends/:id/workspaces", get(list_friend_workspaces).post(create_friend_workspace))
        .route(
            "/friends/:id/workspaces/:ws_id",
            patch(update_friend_workspace).delete(delete_friend_workspace),
        )
        .route(
            "/friends/:id/workspaces/:ws_id/activate",
            post(activate_friend_workspace),
        )
        .route(
            "/friends/:id/workspaces/:ws_id/cli-sessions",
            get(list_workspace_cli_sessions),
        )
        .route(
            "/friends/:id/workspaces/:ws_id/cli-sessions/:session_id/activate",
            post(activate_workspace_cli_session),
        )
        .route(
            "/friends/:id/workspaces/:ws_id/import-codex",
            post(import_workspace_codex_sessions),
        )
        .route(
            "/friends/:id/workspaces/:ws_id/import-claude",
            post(import_workspace_claude_sessions),
        )
        .route(
            "/friends/:id/workspaces/:ws_id/import-cursor",
            post(import_workspace_cursor_sessions),
        )
        .route("/groups", get(list_groups).post(upsert_group))
        .route("/groups/:id", get(get_group))
        .route("/groups/:id/im/inbound", post(group_im_inbound))
        .route(
            "/assistant-policy-templates",
            get(list_assistant_policy_templates).post(upsert_assistant_policy_template),
        )
        .route(
            "/assistant-policy-templates/:id",
            delete(delete_assistant_policy_template),
        )
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
        .route(
            "/conversations/:id/attachments",
            post(attachments::upload_conversation_attachments),
        )
        .route(
            "/uploads/:conv_id/:file_id",
            get(attachments::get_upload),
        )
        .route(
            "/conversations/:conv_id/messages/:msg_id/delegate",
            post(resolve_delegate_message),
        )
        .route(
            "/assistant/global-settings",
            get(get_assistant_global_settings).post(upsert_assistant_global_settings),
        )
        .route(
            "/assistant/global-settings/consolidate",
            post(consolidate_assistant_global_memories),
        )
        .route("/assistant/tenant", get(get_assistant_tenant))
        .route(
            "/agent-dna",
            get(get_agent_dna).put(upsert_agent_dna),
        )
        .route("/agent-dna/preview", get(preview_agent_dna))
        .route("/assistant/:friend_id/memories", get(list_memories).post(add_memory))
        .route(
            "/assistant/:friend_id/memories/stats",
            get(assistant_memory_stats),
        )
        .route(
            "/assistant/:friend_id/memories/recall-preview",
            get(assistant_memory_recall_preview),
        )
        .route(
            "/assistant/:friend_id/memories/:memory_id",
            delete(delete_memory).patch(patch_memory_handler),
        )
        .route("/assistant/:friend_id/skills", get(list_skills))
        .route("/assistant/:friend_id/reflections", get(list_reflections))
        .route(
            "/assistant/:friend_id/todos",
            get(list_assistant_todos).post(create_assistant_todo),
        )
        .route(
            "/assistant/:friend_id/todos/:todo_id",
            post(update_assistant_todo),
        )
        .route("/assistant/:friend_id/todos/run", post(run_assistant_todos_once))
        .route("/assistant/queue/jobs", get(list_assistant_queue_jobs))
        .route("/assistant/queue/stats", get(get_assistant_queue_stats))
        .route("/assistant/queue/replay-failed", post(replay_failed_assistant_queue_jobs))
        .route("/invites", get(list_all_invites).post(create_invite))
        .route("/invites/:id", delete(delete_invite))
        .route("/human/:code/state", get(human_state))
        .route("/human/:code/send", post(human_send))
        .route("/human/:code/typing", post(human_typing))
}

async fn health() -> impl IntoResponse {
    (StatusCode::OK, Json(serde_json::json!({"ok": true})))
}

async fn list_friends(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let auth = crate::auth::resolve_optional_auth(&s, &headers).await?;
    let store = auth.tenant_store(&s);
    let friends = store.list_friends().await?;
    Ok(Json(serde_json::json!({ "friends": friends })))
}

async fn get_friend(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let auth = crate::auth::resolve_optional_auth(&s, &headers).await?;
    let store = auth.tenant_store(&s);
    let f = store
        .get_friend(&id)
        .await?
        .ok_or_else(|| ApiError::NotFound)?;
    Ok(Json(serde_json::json!({ "friend": f })))
}

async fn friend_cli_auth(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let status = s.core.cli_oauth.full_status(&store, &id).await?;
    Ok(Json(serde_json::json!({ "cli_auth": status })))
}

async fn friend_cli_oauth_start(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let snap = s.core.cli_oauth.start(&store, &id).await?;
    let status = s.core.cli_oauth.full_status(&store, &id).await?;
    Ok(Json(serde_json::json!({ "oauth": snap, "cli_auth": status })))
}

async fn friend_cli_oauth_cancel(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    s.core.cli_oauth.cancel(&id).await?;
    let status = s.core.cli_oauth.full_status(&store, &id).await?;
    Ok(Json(serde_json::json!({ "cli_auth": status })))
}

async fn friend_cli_logout(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let status = s.core.cli_oauth.logout(&store, &id).await?;
    Ok(Json(serde_json::json!({ "cli_auth": status })))
}

async fn upsert_friend(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(req): Json<UpsertFriend>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let auth = crate::auth::resolve_optional_auth(&s, &headers).await?;
    let store = auth.tenant_store(&s);
    let f = store.upsert_friend(req).await?;
    s.core.agents.invalidate(&f.id);
    Ok(Json(serde_json::json!({ "friend": f })))
}

async fn delete_friend(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    store.delete_friend(&id).await?;
    s.core.agents.invalidate(&id);
    Ok(Json(serde_json::json!({ "ok": true })))
}

async fn list_friend_workspaces(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    store.ensure_friend_workspaces(&id).await?;
    let workspaces = store.list_workspaces_for_friend(&id).await?;
    let active_workspace_id = store.active_workspace_id_for_friend(&id).await?;
    Ok(Json(serde_json::json!({
        "workspaces": workspaces,
        "active_workspace_id": active_workspace_id,
    })))
}

async fn create_friend_workspace(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
    Json(req): Json<CreateWorkspace>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let ws = store.create_workspace(&id, req).await?;
    s.core.agents.invalidate(&id);
    Ok(Json(serde_json::json!({ "workspace": ws })))
}

async fn update_friend_workspace(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path((id, ws_id)): Path<(String, String)>,
    Json(req): Json<UpdateWorkspace>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let ws = store.get_workspace(&ws_id).await?;
    let ws = ws.ok_or(ApiError::NotFound)?;
    if ws.owner_friend_id != id {
        return Err(ApiError::NotFound);
    }
    let ws = store.update_workspace(&ws_id, req).await?;
    s.core.agents.invalidate(&id);
    Ok(Json(serde_json::json!({ "workspace": ws })))
}

async fn delete_friend_workspace(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path((id, ws_id)): Path<(String, String)>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let ws = store.get_workspace(&ws_id).await?;
    let ws = ws.ok_or(ApiError::NotFound)?;
    if ws.owner_friend_id != id {
        return Err(ApiError::NotFound);
    }
    store.delete_workspace(&ws_id).await?;
    s.core.agents.invalidate(&id);
    Ok(Json(serde_json::json!({ "ok": true })))
}

async fn list_workspace_cli_sessions(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path((id, ws_id)): Path<(String, String)>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let ws = store.get_workspace(&ws_id).await?;
    let ws = ws.ok_or(ApiError::NotFound)?;
    if ws.owner_friend_id != id {
        return Err(ApiError::NotFound);
    }
    let sessions = store.list_cli_sessions(&ws_id).await?;
    Ok(Json(serde_json::json!({ "cli_sessions": sessions })))
}

async fn activate_workspace_cli_session(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path((id, ws_id, session_id)): Path<(String, String, String)>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let ws = store.get_workspace(&ws_id).await?;
    let ws = ws.ok_or(ApiError::NotFound)?;
    if ws.owner_friend_id != id {
        return Err(ApiError::NotFound);
    }
    store.set_active_cli_session(&ws_id, &session_id).await?;
    s.core.agents.invalidate(&id);
    Ok(Json(serde_json::json!({ "ok": true })))
}

#[derive(Debug, Deserialize)]
struct ImportCliBody {
    #[serde(default = "default_true")]
    ingest_memories: bool,
}

async fn import_workspace_codex_sessions(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path((id, ws_id)): Path<(String, String)>,
    Json(body): Json<ImportCliBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    import_workspace_cli(&s, &headers, id, ws_id, "codex", body.ingest_memories).await
}

async fn import_workspace_claude_sessions(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path((id, ws_id)): Path<(String, String)>,
    Json(body): Json<ImportCliBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    import_workspace_cli(&s, &headers, id, ws_id, "claude", body.ingest_memories).await
}

async fn import_workspace_cursor_sessions(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path((id, ws_id)): Path<(String, String)>,
    Json(body): Json<ImportCliBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    import_workspace_cli(&s, &headers, id, ws_id, "cursor", body.ingest_memories).await
}

async fn import_workspace_cli(
    s: &AppState,
    headers: &axum::http::HeaderMap,
    friend_id: String,
    ws_id: String,
    tool: &str,
    ingest_memories: bool,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(s, headers).await?;
    let ws = store.get_workspace(&ws_id).await?;
    let ws = ws.ok_or(ApiError::NotFound)?;
    if ws.owner_friend_id != friend_id {
        return Err(ApiError::NotFound);
    }
    let report = match tool {
        "codex" => store.import_codex_sessions_for_workspace(&ws_id, ingest_memories).await?,
        "claude" => store.import_claude_sessions_for_workspace(&ws_id, ingest_memories).await?,
        "cursor" => store.import_cursor_sessions_for_workspace(&ws_id, ingest_memories).await?,
        _ => return Err(ApiError::BadRequest("unknown import tool".into())),
    };
    s.core.agents.invalidate(&friend_id);
    let sessions = store.list_cli_sessions(&ws_id).await?;
    Ok(Json(serde_json::json!({ "report": report, "tool": tool, "cli_sessions": sessions })))
}

async fn activate_friend_workspace(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path((id, ws_id)): Path<(String, String)>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    store.set_active_workspace(&id, &ws_id).await?;
    s.core.agents.invalidate(&id);
    let active_workspace_id = store.active_workspace_id_for_friend(&id).await?;
    Ok(Json(serde_json::json!({
        "ok": true,
        "active_workspace_id": active_workspace_id,
    })))
}

async fn list_groups(State(s): State<AppState>,
    headers: axum::http::HeaderMap) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let groups = store.list_groups().await?;
    let mut out = Vec::new();
    for g in &groups {
        out.push(group_bundle_json(&store, &s.core.providers, g).await?);
    }
    Ok(Json(serde_json::json!({ "groups": out })))
}

async fn get_group(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let g = store
        .get_group(&id)
        .await?
        .ok_or_else(|| ApiError::NotFound)?;
    let mut bundle = group_bundle_json(&store, &s.core.providers, &g).await?;
    let conv = store.get_or_create_group_conversation(&g.id).await?;
    bundle["conversation_id"] = serde_json::json!(conv.id);
    Ok(Json(bundle))
}

async fn upsert_group(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(mut req): Json<UpsertGroup>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    req.settings.sync_judge_threshold_fields();
    let expert_ids = expert_member_ids_from_upsert(&req.members, &req.member_ids);
    let readiness = validate_group_task_flow_readiness(
        &store,
        &s.core.providers,
        &req.settings,
        &expert_ids,
    )
    .await?;
    if !readiness.errors.is_empty() {
        return Err(ApiError::BadRequest(readiness.errors.join("；")));
    }
    let g = store.upsert_group(req).await?;
    let mut bundle = group_bundle_json(&store, &s.core.providers, &g).await?;
    let conv = store.get_or_create_group_conversation(&g.id).await?;
    bundle["conversation_id"] = serde_json::json!(conv.id);
    Ok(Json(bundle))
}

async fn group_bundle_json(
    store: &seven_chat_agent_core::store::SqliteStore,
    providers: &seven_chat_agent_core::provider::ProviderRegistry,
    g: &seven_chat_agent_core::domain::Group,
) -> Result<serde_json::Value, ApiError> {
    let members = store.list_group_member_configs(&g.id).await?;
    let member_ids: Vec<String> = members.iter().map(|m| m.friend_id.clone()).collect();
    let expert_member_ids: Vec<String> = store.list_group_expert_friend_ids(&g.id).await?;
    let assistant_member_id = store.group_assistant_member_id(&g.id).await?;
    let workspaces = store.list_group_workspaces(&g.id).await?;
    let member_bindings = store.list_group_member_bindings(&g.id).await?;
    let task_flow_readiness = validate_group_task_flow_readiness(
        store,
        providers,
        &g.settings,
        &expert_member_ids,
    )
    .await?;
    let assistant_resolved = store
        .resolve_group_assistant_settings(&g.settings.assistant)
        .await?;
    Ok(serde_json::json!({
        "group": g,
        "member_ids": member_ids,
        "expert_member_ids": expert_member_ids,
        "assistant_member_id": assistant_member_id,
        "assistant_resolved": assistant_resolved,
        "members": members,
        "workspaces": workspaces,
        "member_bindings": member_bindings,
        "task_flow_readiness": task_flow_readiness,
    }))
}

async fn list_assistant_policy_templates(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let templates = store.list_assistant_policy_templates().await?;
    Ok(Json(serde_json::json!({ "templates": templates })))
}

async fn upsert_assistant_policy_template(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(req): Json<seven_chat_agent_core::store::assistant_policy::UpsertAssistantPolicyTemplate>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let t = store.upsert_assistant_policy_template(req).await?;
    Ok(Json(serde_json::json!({ "template": t })))
}

async fn delete_assistant_policy_template(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<StatusCode, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    store.delete_assistant_policy_template(&id).await?;
    Ok(StatusCode::NO_CONTENT)
}

#[derive(Debug, Deserialize)]
struct GroupImInboundBody {
    action: String,
    #[serde(default)]
    content: Option<String>,
    #[serde(default)]
    message_id: Option<String>,
}

async fn group_im_inbound(
    State(s): State<AppState>,
    Path(group_id): Path<String>,
    headers: axum::http::HeaderMap,
    Json(body): Json<GroupImInboundBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let secret = headers
        .get("X-SevenChatAgent-Im-Secret")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    let message = s
        .core
        .dispatcher
        .handle_group_im_inbound(
            &group_id,
            secret,
            &body.action,
            body.content,
            body.message_id,
        )
        .await?;
    Ok(Json(serde_json::json!({ "ok": true, "message": message })))
}

async fn list_providers(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let auth = crate::auth::resolve_optional_auth(&s, &headers).await?;
    let store = auth.tenant_store(&s);
    let providers = store.list_providers().await?;
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
    headers: axum::http::HeaderMap,
    Json(req): Json<UpsertProviderReq>,
) -> Result<Json<serde_json::Value>, ApiError> {
    if req.id.trim().is_empty() {
        return Err(ApiError::BadRequest("provider id is required".into()));
    }
    let auth = crate::auth::resolve_optional_auth(&s, &headers).await?;
    let store = auth.tenant_store(&s);
    let id = req.id.clone();
    let existing = store.get_provider(&id).await?;
    let created_at = existing
        .as_ref()
        .map(|e| e.created_at)
        .unwrap_or_else(chrono::Utc::now);
    let base_url = {
        let t = req.base_url.trim();
        if t.is_empty() {
            existing
                .as_ref()
                .map(|e| e.base_url.clone())
                .ok_or_else(|| ApiError::BadRequest("base_url is required for new provider".into()))?
        } else {
            t.to_string()
        }
    };
    let provider = Provider {
        id,
        kind: if req.kind.trim().is_empty() {
            existing
                .as_ref()
                .map(|e| e.kind.clone())
                .unwrap_or_else(|| "openai_compat".to_string())
        } else {
            req.kind
        },
        display_name: if req.display_name.trim().is_empty() {
            existing
                .as_ref()
                .map(|e| e.display_name.clone())
                .unwrap_or_else(|| req.id)
        } else {
            req.display_name
        },
        base_url,
        default_model: req.default_model,
        capabilities: req.capabilities.unwrap_or_default(),
        price: req.price.unwrap_or_default(),
        enabled: req.enabled,
        created_at,
    };
    store.upsert_provider(&provider).await?;
    s.core
        .providers
        .reload_tenant(store.tenant_id())
        .await?;
    Ok(Json(serde_json::json!({ "provider": provider })))
}

async fn delete_provider(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let auth = crate::auth::resolve_optional_auth(&s, &headers).await?;
    let store = auth.tenant_store(&s);
    store.delete_provider(&id).await?;
    s.core
        .providers
        .reload_tenant(store.tenant_id())
        .await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

#[derive(Debug, Deserialize)]
struct ProviderKeyQuery {
    provider_id: Option<String>,
}

async fn list_provider_keys(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    axum::extract::Query(q): axum::extract::Query<ProviderKeyQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let keys = store.list_provider_keys(q.provider_id.as_deref()).await?;
    Ok(Json(serde_json::json!({ "provider_keys": keys })))
}

async fn upsert_provider_key(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(req): Json<UpsertProviderKey>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let k = store.upsert_provider_key(req).await?;
    s.core.providers.reload_tenant(store.tenant_id()).await?;
    Ok(Json(serde_json::json!({ "provider_key": k })))
}

async fn delete_provider_key(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    store.delete_provider_key(&id).await?;
    s.core.providers.reload_tenant(store.tenant_id()).await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

async fn list_conversations(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let convs = store.list_conversations().await?;
    Ok(Json(serde_json::json!({ "conversations": convs })))
}

async fn get_conversation(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let c = store
        .get_conversation(&id)
        .await?
        .ok_or_else(|| ApiError::NotFound)?;
    Ok(Json(serde_json::json!({ "conversation": c })))
}

async fn list_messages(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let messages = store.list_messages(&id, 500).await?;
    Ok(Json(serde_json::json!({ "messages": messages })))
}

async fn open_dm(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(friend_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let conv = store.get_or_create_dm(&friend_id).await?;
    let messages = store.list_messages(&conv.id, 200).await?;
    Ok(Json(serde_json::json!({
        "conversation": conv,
        "messages": messages,
    })))
}

async fn send_message(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(friend_id): Path<String>,
    Json(body): Json<attachments::SendWithAttachments>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let auth = crate::auth::resolve_optional_auth(&s, &headers).await?;
    let store = auth.tenant_store(&s);
    let conv = store.get_or_create_dm(&friend_id).await?;
    let data_dir = std::env::var("SEVEN_CHAT_AGENT_DATA").unwrap_or_else(|_| "data".into());
    attachments::validate_send_attachments(&data_dir, &conv.id, &body.attachments)?;
    let core = s.core.clone();
    let conv_id = conv.id.clone();
    let content = body.content.clone();
    let attachments = body.attachments.clone();
    let tenant_id = store.tenant_id().to_string();
    let user_id = auth.session().map(|sess| sess.user_id.clone());
    tokio::spawn(async move {
        let run = seven_chat_agent_core::tenant_context::with_active_scope(
            &tenant_id,
            user_id.as_deref(),
            || {
                core.dispatcher
                    .send_user_message_with_attachments(&conv_id, &content, &attachments)
            },
        )
        .await;
        if let Err(e) = run {
            tracing::error!(err = %e, "send_user_message failed");
        }
    });
    Ok(Json(serde_json::json!({ "ok": true, "conversation_id": conv.id })))
}

async fn send_to_conversation(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
    Json(body): Json<attachments::SendWithAttachments>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let auth = crate::auth::resolve_optional_auth(&s, &headers).await?;
    let store = auth.tenant_store(&s);
    let data_dir = std::env::var("SEVEN_CHAT_AGENT_DATA").unwrap_or_else(|_| "data".into());
    attachments::validate_send_attachments(&data_dir, &id, &body.attachments)?;
    let core = s.core.clone();
    let conv_id = id.clone();
    let content = body.content.clone();
    let attachments = body.attachments.clone();
    let tenant_id = store.tenant_id().to_string();
    let user_id = auth.session().map(|sess| sess.user_id.clone());
    tokio::spawn(async move {
        let run = seven_chat_agent_core::tenant_context::with_active_scope(
            &tenant_id,
            user_id.as_deref(),
            || {
                core.dispatcher
                    .send_user_message_with_attachments(&conv_id, &content, &attachments)
            },
        )
        .await;
        if let Err(e) = run {
            tracing::error!(err = %e, "send_user_message failed");
        }
    });
    Ok(Json(serde_json::json!({ "ok": true, "conversation_id": id })))
}

#[derive(Debug, Deserialize)]
struct ResolveDelegateBody {
    approve: bool,
    #[serde(default)]
    content: Option<String>,
}

async fn resolve_delegate_message(
    State(s): State<AppState>,
    Path((conv_id, msg_id)): Path<(String, String)>,
    Json(body): Json<ResolveDelegateBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let message = s
        .core
        .dispatcher
        .resolve_group_delegate(&conv_id, &msg_id, body.approve, body.content)
        .await?;
    Ok(Json(serde_json::json!({ "message": message })))
}

#[derive(Debug, Deserialize)]
struct MemoryQuery {
    kind: Option<String>,
    /// `memo` | `knowledge` — 助理面板分区
    category: Option<String>,
    /// `raw` | `curated`
    tier: Option<String>,
    /// `active` | `archived`
    status: Option<String>,
    scope: Option<String>,
    limit: Option<i64>,
}

async fn get_assistant_global_settings(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let settings = store.get_assistant_global_settings().await?;
    Ok(Json(serde_json::json!({ "settings": settings })))
}

async fn upsert_assistant_global_settings(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(body): Json<AssistantGlobalSettings>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let settings = store.upsert_assistant_global_settings(body).await?;
    Ok(Json(serde_json::json!({ "settings": settings })))
}

async fn get_assistant_tenant(State(s): State<AppState>,
    headers: axum::http::HeaderMap) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    Ok(Json(serde_json::json!({
        "tenant_id": store.tenant_id(),
    })))
}

async fn get_agent_dna(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let dna = store.get_agent_dna().await?;
    Ok(Json(serde_json::json!({ "dna": dna })))
}

async fn upsert_agent_dna(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(body): Json<seven_chat_agent_core::agent_dna::AgentDna>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let session = crate::auth::session_from_request(&s, &headers).await?;
    crate::auth::require_admin(&session)?;
    let store = tenant_store_from_request(&s, &headers).await?;
    let dna = store.upsert_agent_dna(body).await?;
    Ok(Json(serde_json::json!({ "dna": dna })))
}

async fn preview_agent_dna(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let dna = store.get_agent_dna().await?;
    let rendered = seven_chat_agent_core::agent_dna::render_dna_block(&dna);
    Ok(Json(serde_json::json!({ "rendered": rendered, "dna": dna })))
}

async fn consolidate_assistant_global_memories(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let tenant_id = store.tenant_id().to_string();
    let report = seven_chat_agent_core::tenant_context::with_active_tenant(&tenant_id, || async {
        s.core.run_memory_maintenance().await
    })
    .await?;
    store.reset_assistant_observe_streak().await?;
    let settings = store.get_assistant_global_settings().await?;
    Ok(Json(serde_json::json!({
        "ok": true,
        "settings": settings,
        "report": report,
    })))
}

async fn list_memories(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(friend_id): Path<String>,
    axum::extract::Query(q): axum::extract::Query<MemoryQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let limit = q.limit.unwrap_or(100);
    let filter = seven_chat_agent_core::store::memory::ListMemoryFilter {
        tier: q.tier,
        status: q.status,
        scope: q.scope,
        category: q.category,
    };
    let memories = store
        .list_memories_filtered(&friend_id, filter, limit)
        .await?;
    Ok(Json(serde_json::json!({ "memories": memories })))
}

async fn add_memory(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(friend_id): Path<String>,
    Json(mut body): Json<NewMemory>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    body.owner_friend_id = friend_id;
    let m = store.insert_memory(body).await?;
    Ok(Json(serde_json::json!({ "memory": m })))
}

async fn delete_memory(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path((_friend_id, memory_id)): Path<(String, String)>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    store.delete_memory(&memory_id).await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

#[derive(Debug, Deserialize)]
struct PatchMemoryBody {
    kind: Option<String>,
    content: Option<String>,
    weight: Option<f64>,
    pinned: Option<bool>,
    tier: Option<String>,
    scope: Option<String>,
    scope_ref: Option<String>,
    importance: Option<i32>,
    status: Option<String>,
    title: Option<String>,
    summary: Option<String>,
    /// 保存时把原始记忆提升为整理层
    #[serde(default)]
    promote_to_curated: bool,
}

async fn patch_memory_handler(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path((_friend_id, memory_id)): Path<(String, String)>,
    Json(body): Json<PatchMemoryBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let scope_ref = body.scope_ref.as_deref().map(Some);
    let memory = store
        .update_memory(
            &memory_id,
            body.kind.as_deref(),
            body.content.as_deref(),
            body.weight,
            body.pinned,
            body.tier.as_deref(),
            body.scope.as_deref(),
            scope_ref,
            body.importance,
            body.status.as_deref(),
            body.title.as_deref().map(Some),
            body.summary.as_deref().map(Some),
            body.promote_to_curated,
        )
        .await?;
    Ok(Json(serde_json::json!({ "memory": memory })))
}

async fn assistant_memory_stats(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(friend_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let stats = store.memory_stats(&friend_id).await?;
    Ok(Json(serde_json::json!({ "stats": stats })))
}

#[derive(Debug, Deserialize)]
struct RecallPreviewQuery {
    prompt: Option<String>,
    limit: Option<i64>,
    conversation_id: Option<String>,
    friend_id: Option<String>,
    workspace_id: Option<String>,
}

async fn assistant_memory_recall_preview(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(friend_id): Path<String>,
    axum::extract::Query(q): axum::extract::Query<RecallPreviewQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let prompt = q.prompt.unwrap_or_default();
    let limit = q.limit.unwrap_or(8);
    let workspace_id = if let Some(w) = q.workspace_id {
        Some(w)
    } else {
        store
            .get_active_workspace(&friend_id)
            .await?
            .map(|w| w.id)
    };
    let ctx = seven_chat_agent_core::memory_tier::RecallContext {
        conversation_id: q.conversation_id,
        friend_id: q.friend_id,
        workspace_id,
    };
    let memories = store
        .recall_memories_for_turn(&friend_id, &prompt, limit, false, &ctx)
        .await?;
    Ok(Json(serde_json::json!({ "memories": memories, "prompt": prompt })))
}

async fn list_skills(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(friend_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let skills = if let Ok(friend) = store.get_friend(&friend_id).await {
        if let Some(friend) = friend {
            let cfg: seven_chat_agent_core::domain::PtyBackendConfig =
                serde_json::from_value(friend.backend_config).unwrap_or_default();
            let dir = cfg
                .skills_dir
                .filter(|s| !s.trim().is_empty())
                .unwrap_or_else(|| "data/skills".to_string());
            store.sync_skills_from_disk(&friend_id, &dir).await?
        } else {
            store.list_skills(&friend_id).await?
        }
    } else {
        store.list_skills(&friend_id).await?
    };
    Ok(Json(serde_json::json!({ "skills": skills })))
}

async fn list_reflections(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(friend_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let reflections = store.list_reflections(&friend_id, 50).await?;
    Ok(Json(serde_json::json!({ "reflections": reflections })))
}

#[derive(Debug, Deserialize)]
struct AssistantTodoQuery {
    status: Option<String>,
    limit: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct CreateAssistantTodoReq {
    /// 原始自然语言输入（可选）：例如“1分钟后叫我开会”。
    #[serde(default)]
    raw_text: Option<String>,
    title: String,
    #[serde(default)]
    detail: Option<String>,
    #[serde(default = "default_assistant_todo_priority")]
    priority: i64,
    /// 创建后多少秒提醒一次（例如 60 = 1 分钟后）。
    #[serde(default)]
    remind_after_seconds: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct UpdateAssistantTodoReq {
    title: String,
    #[serde(default)]
    detail: Option<String>,
    priority: i64,
    #[serde(default)]
    status: Option<String>,
}

fn default_assistant_todo_priority() -> i64 {
    1
}

async fn list_assistant_todos(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(friend_id): Path<String>,
    axum::extract::Query(q): axum::extract::Query<AssistantTodoQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let status = q
        .status
        .as_deref()
        .map(AssistantTodoStatus::parse);
    let todos = store
        .list_assistant_todos(&friend_id, status, q.limit.unwrap_or(200))
        .await?;
    Ok(Json(serde_json::json!({ "todos": todos })))
}

async fn create_assistant_todo(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(friend_id): Path<String>,
    Json(body): Json<CreateAssistantTodoReq>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let intent = if let Some(raw) = body.raw_text.as_deref().filter(|x| !x.trim().is_empty()) {
        parse_quick_intent(raw).unwrap_or_else(|| AssistantIntent::TodoCreate {
            title: if body.title.trim().is_empty() {
                raw.trim().to_string()
            } else {
                body.title.trim().to_string()
            },
            detail: body.detail.as_deref().map(str::trim).filter(|x| !x.is_empty()).map(str::to_string),
            priority: body.priority,
            remind_after_seconds: body.remind_after_seconds,
        })
    } else {
        if body.title.trim().is_empty() {
            return Err(ApiError::BadRequest("todo title is required".into()));
        }
        AssistantIntent::TodoCreate {
            title: body.title.trim().to_string(),
            detail: body.detail.as_deref().map(str::trim).filter(|x| !x.is_empty()).map(str::to_string),
            priority: body.priority,
            remind_after_seconds: body.remind_after_seconds,
        }
    };
    let plan = plan_from_intent(&friend_id, intent);
    let tenant_id = store.tenant_id().to_string();
    let core = s.core.clone();
    let friend_id = friend_id.clone();
    let todo = seven_chat_agent_core::tenant_context::with_active_tenant(&tenant_id, || async {
        core.execute_assistant_task_plan(&friend_id, &plan).await
    })
    .await?
    .ok_or_else(|| ApiError::BadRequest("planner created no todo".into()))?;
    Ok(Json(serde_json::json!({ "todo": todo, "intent": format!("{:?}", plan.intent) })))
}

async fn update_assistant_todo(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path((_friend_id, todo_id)): Path<(String, String)>,
    Json(body): Json<UpdateAssistantTodoReq>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    if body.title.trim().is_empty() {
        return Err(ApiError::BadRequest("todo title is required".into()));
    }
    let status = body.status.as_deref().map(AssistantTodoStatus::parse);
    let todo = store
        .update_assistant_todo(
            &todo_id,
            body.title.trim(),
            body.detail.as_deref().map(str::trim).filter(|x| !x.is_empty()),
            body.priority,
            status,
        )
        .await?
        .ok_or(ApiError::NotFound)?;
    Ok(Json(serde_json::json!({ "todo": todo })))
}

async fn run_assistant_todos_once(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(friend_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let tenant_id = store.tenant_id().to_string();
    let core = s.core.clone();
    seven_chat_agent_core::tenant_context::with_active_tenant(&tenant_id, || async {
        core.enqueue_assistant_task(AssistantQueueTask::IdleTick).await
    })
    .await?;
    let todos = store
        .list_assistant_todos(&friend_id, None, 200)
        .await?;
    Ok(Json(serde_json::json!({ "ok": true, "queued": true, "todos": todos })))
}

#[derive(Debug, Deserialize)]
struct AssistantQueueQuery {
    status: Option<String>,
    limit: Option<i64>,
}

async fn list_assistant_queue_jobs(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    axum::extract::Query(q): axum::extract::Query<AssistantQueueQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let jobs = store
        .list_assistant_queue_jobs(q.status.as_deref(), q.limit.unwrap_or(200))
        .await?;
    Ok(Json(serde_json::json!({ "jobs": jobs })))
}

async fn get_assistant_queue_stats(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let stats = store.assistant_queue_stats().await?;
    Ok(Json(serde_json::json!({ "stats": stats })))
}

#[derive(Debug, Deserialize)]
struct ReplayQueueReq {
    #[serde(default = "default_replay_limit")]
    limit: i64,
}

fn default_replay_limit() -> i64 {
    100
}

async fn replay_failed_assistant_queue_jobs(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(body): Json<ReplayQueueReq>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let replayed = store.replay_failed_assistant_jobs(body.limit).await?;
    Ok(Json(serde_json::json!({ "ok": true, "replayed": replayed })))
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
    headers: axum::http::HeaderMap,
    Json(body): Json<CreateInviteBody>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    let invite = store
        .create_invite(&body.friend_id, body.expires_in_hours)
        .await?;
    Ok(Json(serde_json::json!({ "invite": invite })))
}

async fn list_all_invites(
    State(s): State<AppState>,
    headers: axum::http::HeaderMap,
    axum::extract::Query(q): axum::extract::Query<InviteQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    if let Some(fid) = q.friend_id {
        let invites = store.list_invites(&fid).await?;
        return Ok(Json(serde_json::json!({ "invites": invites })));
    }
    let friends = store.list_friends().await?;
    let mut all = Vec::new();
    for f in friends {
        if f.backend_kind == seven_chat_agent_core::domain::BackendKind::Human {
            let invites = store.list_invites(&f.id).await?;
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
    headers: axum::http::HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = tenant_store_from_request(&s, &headers).await?;
    store.delete_invite(&id).await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}

async fn store_for_invite(
    s: &AppState,
    code: &str,
) -> Result<seven_chat_agent_core::store::SqliteStore, ApiError> {
    let invite = s
        .core
        .store
        .get_invite_by_code(code)
        .await?
        .ok_or(ApiError::NotFound)?;
    let tid = s
        .core
        .store
        .friend_tenant_id(&invite.friend_id)
        .await?
        .unwrap_or_else(|| s.core.store.tenant_id().to_string());
    Ok(s.core.store.for_tenant(&tid))
}

async fn human_state(
    State(s): State<AppState>,
    Path(code): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let store = store_for_invite(&s, &code).await?;
    let invite = match s.core.store.get_invite_by_code(&code).await? {
        Some(i) => i,
        None => return Err(ApiError::NotFound),
    };
    if invite.used_at.is_none() {
        let _ = s.core.store.consume_invite(&code).await;
    }
    let friend = store
        .get_friend(&invite.friend_id)
        .await?
        .ok_or(ApiError::NotFound)?;
    let session = store
        .upsert_human_session(&friend.id, "invite", None)
        .await?;
    let convs = store.list_conversations().await?;
    let messages = if let Some(c) = convs.iter().find(|c| c.target_id == friend.id) {
        store.list_messages(&c.id, 200).await?
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
    let store = store_for_invite(&s, &code).await?;
    let invite = s
        .core
        .store
        .get_invite_by_code(&code)
        .await?
        .ok_or(ApiError::NotFound)?;
    let friend_id = invite.friend_id.clone();
    let conv_id = match body.conversation_id {
        Some(id) => id,
        None => store.get_or_create_dm(&friend_id).await?.id,
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
    let store = store_for_invite(&s, &code).await?;
    let invite = s
        .core
        .store
        .get_invite_by_code(&code)
        .await?
        .ok_or(ApiError::NotFound)?;
    let dur = body.duration_ms.unwrap_or(3000);
    store.set_human_typing(&invite.friend_id, dur).await?;
    Ok(Json(serde_json::json!({ "ok": true })))
}
