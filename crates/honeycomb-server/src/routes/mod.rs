use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::routing::{delete, get, post};
use axum::{Json, Router};
use honeycomb_core::domain::{
    AssistantGlobalSettings, AssistantTodoStatus, Provider, ProviderCapabilities, ProviderPrice,
};
use honeycomb_core::assistant_intent::{AssistantIntent, parse_quick_intent};
use honeycomb_core::assistant_task_planner::plan_from_intent;
use honeycomb_core::store::friend::UpsertFriend;
use honeycomb_core::group_validate::{
    expert_member_ids_from_upsert, validate_group_task_flow_readiness,
};
use honeycomb_core::store::group::UpsertGroup;
use honeycomb_core::{AssistantQueueTask, Honeycomb};
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
        .route("/friends/:id/cli_auth", get(friend_cli_auth))
        .route("/friends/:id/cli_auth/oauth/start", post(friend_cli_oauth_start))
        .route("/friends/:id/cli_auth/oauth/cancel", post(friend_cli_oauth_cancel))
        .route("/friends/:id/cli_auth/logout", post(friend_cli_logout))
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
        .route("/assistant/:friend_id/memories", get(list_memories).post(add_memory))
        .route("/assistant/:friend_id/memories/:memory_id", delete(delete_memory))
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

async fn friend_cli_auth(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let status = s.core.cli_oauth.full_status(&s.core.store, &id).await?;
    Ok(Json(serde_json::json!({ "cli_auth": status })))
}

async fn friend_cli_oauth_start(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let snap = s.core.cli_oauth.start(&s.core.store, &id).await?;
    let status = s.core.cli_oauth.full_status(&s.core.store, &id).await?;
    Ok(Json(serde_json::json!({ "oauth": snap, "cli_auth": status })))
}

async fn friend_cli_oauth_cancel(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    s.core.cli_oauth.cancel(&id).await?;
    let status = s.core.cli_oauth.full_status(&s.core.store, &id).await?;
    Ok(Json(serde_json::json!({ "cli_auth": status })))
}

async fn friend_cli_logout(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let status = s.core.cli_oauth.logout(&s.core.store, &id).await?;
    Ok(Json(serde_json::json!({ "cli_auth": status })))
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
        out.push(group_bundle_json(&s.core, g).await?);
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
    let mut bundle = group_bundle_json(&s.core, &g).await?;
    let conv = s.core.store.get_or_create_group_conversation(&g.id).await?;
    bundle["conversation_id"] = serde_json::json!(conv.id);
    Ok(Json(bundle))
}

async fn upsert_group(
    State(s): State<AppState>,
    Json(mut req): Json<UpsertGroup>,
) -> Result<Json<serde_json::Value>, ApiError> {
    req.settings.sync_judge_threshold_fields();
    let expert_ids = expert_member_ids_from_upsert(&req.members, &req.member_ids);
    let readiness = validate_group_task_flow_readiness(
        &s.core.store,
        &s.core.providers,
        &req.settings,
        &expert_ids,
    )
    .await?;
    if !readiness.errors.is_empty() {
        return Err(ApiError::BadRequest(readiness.errors.join("；")));
    }
    let g = s.core.store.upsert_group(req).await?;
    let mut bundle = group_bundle_json(&s.core, &g).await?;
    let conv = s.core.store.get_or_create_group_conversation(&g.id).await?;
    bundle["conversation_id"] = serde_json::json!(conv.id);
    Ok(Json(bundle))
}

async fn group_bundle_json(
    core: &Honeycomb,
    g: &honeycomb_core::domain::Group,
) -> Result<serde_json::Value, ApiError> {
    let members = core.store.list_group_member_configs(&g.id).await?;
    let member_ids: Vec<String> = members.iter().map(|m| m.friend_id.clone()).collect();
    let expert_member_ids: Vec<String> = core.store.list_group_expert_friend_ids(&g.id).await?;
    let assistant_member_id = core.store.group_assistant_member_id(&g.id).await?;
    let task_flow_readiness = validate_group_task_flow_readiness(
        &core.store,
        &core.providers,
        &g.settings,
        &expert_member_ids,
    )
    .await?;
    let assistant_resolved = core
        .store
        .resolve_group_assistant_settings(&g.settings.assistant)
        .await?;
    Ok(serde_json::json!({
        "group": g,
        "member_ids": member_ids,
        "expert_member_ids": expert_member_ids,
        "assistant_member_id": assistant_member_id,
        "assistant_resolved": assistant_resolved,
        "members": members,
        "task_flow_readiness": task_flow_readiness,
    }))
}

async fn list_assistant_policy_templates(
    State(s): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let templates = s.core.store.list_assistant_policy_templates().await?;
    Ok(Json(serde_json::json!({ "templates": templates })))
}

async fn upsert_assistant_policy_template(
    State(s): State<AppState>,
    Json(req): Json<honeycomb_core::store::assistant_policy::UpsertAssistantPolicyTemplate>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let t = s.core.store.upsert_assistant_policy_template(req).await?;
    Ok(Json(serde_json::json!({ "template": t })))
}

async fn delete_assistant_policy_template(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<StatusCode, ApiError> {
    s.core.store.delete_assistant_policy_template(&id).await?;
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
        .get("X-Honeycomb-Im-Secret")
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
    let id = req.id.clone();
    let existing = s.core.store.get_provider(&id).await?;
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
    limit: Option<i64>,
}

async fn get_assistant_global_settings(
    State(s): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let settings = s.core.store.get_assistant_global_settings().await?;
    Ok(Json(serde_json::json!({ "settings": settings })))
}

async fn upsert_assistant_global_settings(
    State(s): State<AppState>,
    Json(body): Json<AssistantGlobalSettings>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let settings = s.core.store.upsert_assistant_global_settings(body).await?;
    Ok(Json(serde_json::json!({ "settings": settings })))
}

async fn consolidate_assistant_global_memories(
    State(s): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    s.core.store.consolidate_assistant_memories().await?;
    let settings = s.core.store.get_assistant_global_settings().await?;
    Ok(Json(serde_json::json!({ "ok": true, "settings": settings })))
}

async fn list_memories(
    State(s): State<AppState>,
    Path(friend_id): Path<String>,
    axum::extract::Query(q): axum::extract::Query<MemoryQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let limit = q.limit.unwrap_or(100);
    let memories = if q.category.is_some() {
        s.core
            .store
            .list_memories_by_category(&friend_id, q.category.as_deref(), limit)
            .await?
    } else {
        s.core
            .store
            .list_memories(&friend_id, q.kind.as_deref(), limit)
            .await?
    };
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
    let skills = if let Ok(friend) = s.core.store.get_friend(&friend_id).await {
        if let Some(friend) = friend {
            let cfg: honeycomb_core::domain::PtyBackendConfig =
                serde_json::from_value(friend.backend_config).unwrap_or_default();
            let dir = cfg
                .skills_dir
                .filter(|s| !s.trim().is_empty())
                .unwrap_or_else(|| "data/skills".to_string());
            s.core
                .store
                .sync_skills_from_disk(&friend_id, &dir)
                .await?
        } else {
            s.core.store.list_skills(&friend_id).await?
        }
    } else {
        s.core.store.list_skills(&friend_id).await?
    };
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
    Path(friend_id): Path<String>,
    axum::extract::Query(q): axum::extract::Query<AssistantTodoQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let status = q
        .status
        .as_deref()
        .map(AssistantTodoStatus::parse);
    let todos = s
        .core
        .store
        .list_assistant_todos(&friend_id, status, q.limit.unwrap_or(200))
        .await?;
    Ok(Json(serde_json::json!({ "todos": todos })))
}

async fn create_assistant_todo(
    State(s): State<AppState>,
    Path(friend_id): Path<String>,
    Json(body): Json<CreateAssistantTodoReq>,
) -> Result<Json<serde_json::Value>, ApiError> {
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
    let todo = s
        .core
        .execute_assistant_task_plan(&friend_id, &plan)
        .await?
        .ok_or_else(|| ApiError::BadRequest("planner created no todo".into()))?;
    Ok(Json(serde_json::json!({ "todo": todo, "intent": format!("{:?}", plan.intent) })))
}

async fn update_assistant_todo(
    State(s): State<AppState>,
    Path((_friend_id, todo_id)): Path<(String, String)>,
    Json(body): Json<UpdateAssistantTodoReq>,
) -> Result<Json<serde_json::Value>, ApiError> {
    if body.title.trim().is_empty() {
        return Err(ApiError::BadRequest("todo title is required".into()));
    }
    let status = body.status.as_deref().map(AssistantTodoStatus::parse);
    let todo = s
        .core
        .store
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
    Path(friend_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    s.core
        .enqueue_assistant_task(AssistantQueueTask::IdleTick)
        .await?;
    let todos = s
        .core
        .store
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
    axum::extract::Query(q): axum::extract::Query<AssistantQueueQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let jobs = s
        .core
        .store
        .list_assistant_queue_jobs(q.status.as_deref(), q.limit.unwrap_or(200))
        .await?;
    Ok(Json(serde_json::json!({ "jobs": jobs })))
}

async fn get_assistant_queue_stats(
    State(s): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let stats = s.core.store.assistant_queue_stats().await?;
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
    Json(body): Json<ReplayQueueReq>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let replayed = s.core.store.replay_failed_assistant_jobs(body.limit).await?;
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
