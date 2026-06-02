use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::State;
use axum::response::IntoResponse;
use futures::{SinkExt, StreamExt};
use serde::Deserialize;

use crate::state::AppState;
use seven_chat_agent_core::group_validate::{
    expert_member_ids_from_upsert, validate_group_task_flow_readiness,
};
use seven_chat_agent_core::store::friend::UpsertFriend;
use seven_chat_agent_core::store::group::UpsertGroup;
use seven_chat_agent_core::store::memory::NewMemory;
use seven_chat_agent_core::store::workspace::CreateWorkspace;
use seven_chat_agent_core::store::provider::UpsertProviderKey;

#[derive(Debug, Deserialize)]
struct WsApiReq {
    id: String,
    method: String,
    #[serde(default)]
    params: serde_json::Value,
}

pub async fn ws_api_handler(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_ws_api(socket, state))
}

async fn handle_ws_api(socket: WebSocket, state: AppState) {
    let (mut sender, mut receiver) = socket.split();
    while let Some(Ok(msg)) = receiver.next().await {
        let Message::Text(text) = msg else {
            continue;
        };
        let req: WsApiReq = match serde_json::from_str(&text) {
            Ok(v) => v,
            Err(e) => {
                let _ = sender
                    .send(Message::Text(
                        serde_json::json!({"id":"","ok":false,"error":format!("bad request: {e}")})
                            .to_string(),
                    ))
                    .await;
                continue;
            }
        };
        let result = handle_method(&state, &req.method, req.params).await;
        let resp = match result {
            Ok(v) => serde_json::json!({"id": req.id, "ok": true, "result": v}),
            Err(e) => serde_json::json!({"id": req.id, "ok": false, "error": e}),
        };
        if sender.send(Message::Text(resp.to_string())).await.is_err() {
            break;
        }
    }
}

async fn handle_method(
    state: &AppState,
    method: &str,
    params: serde_json::Value,
) -> std::result::Result<serde_json::Value, String> {
    let core = &state.core;
    let store = if matches!(
        method,
        "authStatus"
            | "register"
            | "login"
            | "previewTenantInvite"
            | "createCliRelayPairingToken"
            | "listCliRelays"
    ) {
        core.store.as_ref().clone()
    } else {
        resolve_tenant_store(state, &params).await?
    };
    match method {
        "authStatus" => Ok(serde_json::json!({
            "auth_required": seven_chat_agent_core::auth::auth_required(),
        })),
        "register" => {
            let body: seven_chat_agent_core::store::user::RegisterUser =
                serde_json::from_value(params).map_err(|e| e.to_string())?;
            let auth = store.register_user(body).await.map_err(|e| e.to_string())?;
            core.providers
                .reload_tenant(&auth.tenant_id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "auth": auth }))
        }
        "login" => {
            let body: seven_chat_agent_core::store::user::LoginUser =
                serde_json::from_value(params).map_err(|e| e.to_string())?;
            let auth = store.login_user(body).await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "auth": auth }))
        }
        "logout" => {
            let token = params
                .get("auth_token")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "auth_token required".to_string())?;
            store.logout_session(token).await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true }))
        }
        "me" => {
            let token = params
                .get("auth_token")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "auth_token required".to_string())?;
            let session = store
                .resolve_session(token)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "invalid session".to_string())?;
            let user = store
                .get_user_by_id(&session.user_id)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "user not found".to_string())?;
            Ok(serde_json::json!({
                "user": user.public(),
                "tenant_id": session.tenant_id,
            }))
        }
        "health" => Ok(serde_json::json!({ "ok": true })),
        "listFriends" => {
            let friends = store.list_friends().await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "friends": friends }))
        }
        "getFriend" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            let friend = store
                .get_friend(id)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "friend not found".to_string())?;
            Ok(serde_json::json!({ "friend": friend }))
        }
        "getFriendCliAuth" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            let cli_auth = core
                .cli_oauth
                .full_status(&store, id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "cli_auth": cli_auth }))
        }
        "startFriendCliOAuth" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            let oauth = core
                .cli_oauth
                .start(&store, id)
                .await
                .map_err(|e| e.to_string())?;
            let cli_auth = core
                .cli_oauth
                .full_status(&store, id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "oauth": oauth, "cli_auth": cli_auth }))
        }
        "cancelFriendCliOAuth" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            core.cli_oauth.cancel(id).await.map_err(|e| e.to_string())?;
            let cli_auth = core
                .cli_oauth
                .full_status(&store, id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "cli_auth": cli_auth }))
        }
        "logoutFriendCli" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            let cli_auth = core
                .cli_oauth
                .logout(&store, id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "cli_auth": cli_auth }))
        }
        "upsertFriend" => {
            let req: UpsertFriend = serde_json::from_value(params).map_err(|e| e.to_string())?;
            let friend = store.upsert_friend(req).await.map_err(|e| e.to_string())?;
            core.agents.invalidate(&friend.id);
            Ok(serde_json::json!({ "friend": friend }))
        }
        "listFriendWorkspaces" => {
            let id = params
                .get("id")
                .or_else(|| params.get("friend_id"))
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            store
                .ensure_friend_workspaces(id)
                .await
                .map_err(|e| e.to_string())?;
            let workspaces = store
                .list_workspaces_for_friend(id)
                .await
                .map_err(|e| e.to_string())?;
            let active_workspace_id = store
                .active_workspace_id_for_friend(id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({
                "workspaces": workspaces,
                "active_workspace_id": active_workspace_id,
            }))
        }
        "createFriendWorkspace" => {
            let id = params
                .get("id")
                .or_else(|| params.get("friend_id"))
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            let req = CreateWorkspace {
                name: params
                    .get("name")
                    .and_then(|v| v.as_str())
                    .unwrap_or("新工作区")
                    .to_string(),
                path: params
                    .get("path")
                    .and_then(|v| v.as_str())
                    .map(String::from),
            };
            let ws = store
                .create_workspace(id, req)
                .await
                .map_err(|e| e.to_string())?;
            core.agents.invalidate(id);
            Ok(serde_json::json!({ "workspace": ws }))
        }
        "activateFriendWorkspace" => {
            let id = params
                .get("id")
                .or_else(|| params.get("friend_id"))
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            let ws_id = params
                .get("workspace_id")
                .or_else(|| params.get("ws_id"))
                .and_then(|v| v.as_str())
                .ok_or_else(|| "workspace_id required".to_string())?;
            store
                .set_active_workspace(id, ws_id)
                .await
                .map_err(|e| e.to_string())?;
            core.agents.invalidate(id);
            let active_workspace_id = store
                .active_workspace_id_for_friend(id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({
                "ok": true,
                "active_workspace_id": active_workspace_id,
            }))
        }
        "listWorkspaceCliSessions" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let ws_id = params
                .get("workspace_id")
                .or_else(|| params.get("ws_id"))
                .and_then(|v| v.as_str())
                .ok_or_else(|| "workspace_id required".to_string())?;
            let ws = store
                .get_workspace(ws_id)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "workspace not found".to_string())?;
            if ws.owner_friend_id != friend_id {
                return Err("workspace not found".to_string());
            }
            let cli_sessions = store
                .list_cli_sessions(ws_id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "cli_sessions": cli_sessions }))
        }
        "activateWorkspaceCliSession" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let ws_id = params
                .get("workspace_id")
                .or_else(|| params.get("ws_id"))
                .and_then(|v| v.as_str())
                .ok_or_else(|| "workspace_id required".to_string())?;
            let session_id = params
                .get("session_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "session_id required".to_string())?;
            let ws = store
                .get_workspace(ws_id)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "workspace not found".to_string())?;
            if ws.owner_friend_id != friend_id {
                return Err("workspace not found".to_string());
            }
            store
                .set_active_cli_session(ws_id, session_id)
                .await
                .map_err(|e| e.to_string())?;
            core.agents.invalidate(friend_id);
            Ok(serde_json::json!({ "ok": true }))
        }
        "importWorkspaceCodexSessions" | "importWorkspaceCliSessions" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let ws_id = params
                .get("workspace_id")
                .or_else(|| params.get("ws_id"))
                .and_then(|v| v.as_str())
                .ok_or_else(|| "workspace_id required".to_string())?;
            let tool = params
                .get("tool")
                .and_then(|v| v.as_str())
                .unwrap_or("codex");
            let ingest = params
                .get("ingest_memories")
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            let ws = store
                .get_workspace(ws_id)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "workspace not found".to_string())?;
            if ws.owner_friend_id != friend_id {
                return Err("workspace not found".to_string());
            }
            let report = match tool {
                "codex" => store
                    .import_codex_sessions_for_workspace(ws_id, ingest)
                    .await
                    .map_err(|e| e.to_string())?,
                "claude" => store
                    .import_claude_sessions_for_workspace(ws_id, ingest)
                    .await
                    .map_err(|e| e.to_string())?,
                "cursor" => store
                    .import_cursor_sessions_for_workspace(ws_id, ingest)
                    .await
                    .map_err(|e| e.to_string())?,
                _ => return Err(format!("unknown tool: {tool}")),
            };
            core.agents.invalidate(friend_id);
            let cli_sessions = store
                .list_cli_sessions(ws_id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "report": report, "tool": tool, "cli_sessions": cli_sessions }))
        }
        "deleteFriendWorkspace" => {
            let ws_id = params
                .get("workspace_id")
                .or_else(|| params.get("ws_id"))
                .and_then(|v| v.as_str())
                .ok_or_else(|| "workspace_id required".to_string())?;
            let ws = store
                .get_workspace(ws_id)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "workspace not found".to_string())?;
            store
                .delete_workspace(ws_id)
                .await
                .map_err(|e| e.to_string())?;
            core.agents.invalidate(&ws.owner_friend_id);
            Ok(serde_json::json!({ "ok": true }))
        }
        "deleteFriend" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            store.delete_friend(id).await.map_err(|e| e.to_string())?;
            core.agents.invalidate(id);
            Ok(serde_json::json!({ "ok": true }))
        }
        "listGroups" => {
            let groups = store.list_groups().await.map_err(|e| e.to_string())?;
            let mut out = Vec::new();
            for g in &groups {
                out.push(
                    group_bundle_json(&store, &core.providers, g)
                        .await
                        .map_err(|e| e.to_string())?,
                );
            }
            Ok(serde_json::json!({ "groups": out }))
        }
        "getGroup" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            let g = store
                .get_group(id)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "group not found".to_string())?;
            let mut bundle = group_bundle_json(&store, &core.providers, &g)
                .await
                .map_err(|e| e.to_string())?;
            let conv = store
                .get_or_create_group_conversation(&g.id)
                .await
                .map_err(|e| e.to_string())?;
            bundle["conversation_id"] = serde_json::json!(conv.id);
            Ok(bundle)
        }
        "upsertGroup" => {
            let mut req: UpsertGroup = serde_json::from_value(params).map_err(|e| e.to_string())?;
            req.settings.sync_judge_threshold_fields();
            let expert_ids = expert_member_ids_from_upsert(&req.members, &req.member_ids);
            let readiness = validate_group_task_flow_readiness(
                &store,
                &core.providers,
                &req.settings,
                &expert_ids,
            )
            .await
            .map_err(|e| e.to_string())?;
            if !readiness.errors.is_empty() {
                return Err(readiness.errors.join("；"));
            }
            let g = store.upsert_group(req).await.map_err(|e| e.to_string())?;
            let mut bundle = group_bundle_json(&store, &core.providers, &g)
                .await
                .map_err(|e| e.to_string())?;
            let conv = store
                .get_or_create_group_conversation(&g.id)
                .await
                .map_err(|e| e.to_string())?;
            bundle["conversation_id"] = serde_json::json!(conv.id);
            Ok(bundle)
        }
        "listProviders" => {
            let providers = store.list_providers().await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "providers": providers }))
        }
        "upsertProvider" => {
            let req = params;
            let id = req
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "provider id required".to_string())?;
            let existing = store
                .get_provider(id)
                .await
                .map_err(|e| e.to_string())?;
            let created_at = existing
                .as_ref()
                .map(|e| e.created_at)
                .unwrap_or_else(chrono::Utc::now);
            let base_url_in = req
                .get("base_url")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .trim()
                .to_string();
            let base_url = if base_url_in.is_empty() {
                existing
                    .as_ref()
                    .map(|e| e.base_url.clone())
                    .ok_or_else(|| "base_url is required for new provider".to_string())?
            } else {
                base_url_in
            };
            let provider = seven_chat_agent_core::domain::Provider {
                id: id.to_string(),
                kind: req
                    .get("kind")
                    .and_then(|v| v.as_str())
                    .unwrap_or_else(|| {
                        existing
                            .as_ref()
                            .map(|e| e.kind.as_str())
                            .unwrap_or("openai_compat")
                    })
                    .to_string(),
                display_name: req
                    .get("display_name")
                    .and_then(|v| v.as_str())
                    .unwrap_or_else(|| {
                        existing
                            .as_ref()
                            .map(|e| e.display_name.as_str())
                            .unwrap_or(id)
                    })
                    .to_string(),
                base_url,
                default_model: req
                    .get("default_model")
                    .and_then(|v| v.as_str())
                    .map(str::to_string),
                capabilities: serde_json::from_value(
                    req.get("capabilities")
                        .cloned()
                        .unwrap_or(serde_json::Value::Null),
                )
                .unwrap_or_default(),
                price: serde_json::from_value(
                    req.get("price").cloned().unwrap_or(serde_json::Value::Null),
                )
                .unwrap_or_default(),
                enabled: req.get("enabled").and_then(|v| v.as_bool()).unwrap_or(true),
                created_at,
            };
            store
                .upsert_provider(&provider)
                .await
                .map_err(|e| e.to_string())?;
            core.providers
                .reload_tenant(store.tenant_id())
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "provider": provider }))
        }
        "deleteProvider" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            store.delete_provider(id).await.map_err(|e| e.to_string())?;
            core.providers
                .reload_tenant(store.tenant_id())
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true }))
        }
        "upsertProviderKey" => {
            let req: UpsertProviderKey =
                serde_json::from_value(params).map_err(|e| e.to_string())?;
            let provider_key = store
                .upsert_provider_key(req)
                .await
                .map_err(|e| e.to_string())?;
            core.providers
                .reload_tenant(store.tenant_id())
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "provider_key": provider_key }))
        }
        "deleteProviderKey" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            store
                .delete_provider_key(id)
                .await
                .map_err(|e| e.to_string())?;
            core.providers
                .reload_tenant(store.tenant_id())
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true }))
        }
        "resolveDelegate" => {
            let conversation_id = params
                .get("conversation_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "conversation_id required".to_string())?;
            let message_id = params
                .get("message_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "message_id required".to_string())?;
            let approve = params
                .get("approve")
                .and_then(|v| v.as_bool())
                .ok_or_else(|| "approve required".to_string())?;
            let content = params.get("content").and_then(|v| v.as_str()).map(str::to_string);
            let message = core
                .dispatcher
                .resolve_group_delegate(conversation_id, message_id, approve, content)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "message": message }))
        }
        "listAssistantPolicyTemplates" => {
            let templates = store
                .list_assistant_policy_templates()
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "templates": templates }))
        }
        "addAssistantMemory" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let mut body: NewMemory = serde_json::from_value(
                params.get("body").cloned().ok_or_else(|| "body required".to_string())?,
            )
            .map_err(|e| e.to_string())?;
            body.owner_friend_id = friend_id.to_string();
            let memory = store.insert_memory(body).await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "memory": memory }))
        }
        "deleteAssistantMemory" => {
            let memory_id = params
                .get("memory_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "memory_id required".to_string())?;
            store
                .delete_memory(memory_id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true }))
        }
        "listProviderKeys" => {
            let provider_id = params.get("provider_id").and_then(|v| v.as_str());
            let provider_keys = store
                .list_provider_keys(provider_id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "provider_keys": provider_keys }))
        }
        "openDm" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let conversation = store
                .get_or_create_dm(friend_id)
                .await
                .map_err(|e| e.to_string())?;
            let messages = store
                .list_messages(&conversation.id, 200)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "conversation": conversation, "messages": messages }))
        }
        "sendDm" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let content = params
                .get("content")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let attachments: Vec<seven_chat_agent_core::domain::MessageAttachment> =
                params
                    .get("attachments")
                    .and_then(|v| serde_json::from_value(v.clone()).ok())
                    .unwrap_or_default();
            let conv = store
                .get_or_create_dm(friend_id)
                .await
                .map_err(|e| e.to_string())?;
            let data_dir =
                std::env::var("SEVEN_CHAT_AGENT_DATA").unwrap_or_else(|_| "data".into());
            seven_chat_agent_core::attachment::validate_attachments(
                &data_dir,
                &conv.id,
                &attachments,
            )
            .map_err(|e| e.to_string())?;
            let tenant_id = store.tenant_id().to_string();
            let user_id = store.user_id().map(str::to_string);
            seven_chat_agent_core::tenant_context::with_active_scope(
                &tenant_id,
                user_id.as_deref(),
                || {
                    core.dispatcher.send_user_message_with_attachments(
                        &conv.id,
                        &content,
                        &attachments,
                    )
                },
            )
            .await
            .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true, "conversation_id": conv.id }))
        }
        "listConversationMessages" => {
            let id = params
                .get("conversation_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "conversation_id required".to_string())?;
            let messages = store
                .list_messages(id, 500)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "messages": messages }))
        }
        "sendToConversation" => {
            let id = params
                .get("conversation_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "conversation_id required".to_string())?;
            let content = params
                .get("content")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let attachments: Vec<seven_chat_agent_core::domain::MessageAttachment> =
                params
                    .get("attachments")
                    .and_then(|v| serde_json::from_value(v.clone()).ok())
                    .unwrap_or_default();
            let data_dir =
                std::env::var("SEVEN_CHAT_AGENT_DATA").unwrap_or_else(|_| "data".into());
            seven_chat_agent_core::attachment::validate_attachments(&data_dir, id, &attachments)
                .map_err(|e| e.to_string())?;
            let tenant_id = store.tenant_id().to_string();
            let user_id = store.user_id().map(str::to_string);
            seven_chat_agent_core::tenant_context::with_active_scope(
                &tenant_id,
                user_id.as_deref(),
                || {
                    core.dispatcher
                        .send_user_message_with_attachments(id, &content, &attachments)
                },
            )
            .await
            .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true, "conversation_id": id }))
        }
        "getAssistantGlobalSettings" => {
            let settings = store
                .get_assistant_global_settings()
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "settings": settings }))
        }
        "upsertAssistantGlobalSettings" => {
            let body: seven_chat_agent_core::domain::AssistantGlobalSettings =
                serde_json::from_value(params).map_err(|e| e.to_string())?;
            let settings = store
                .upsert_assistant_global_settings(body)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "settings": settings }))
        }
        "consolidateAssistantMemories" => {
            let tenant_id = store.tenant_id().to_string();
            let report = seven_chat_agent_core::tenant_context::with_active_tenant(&tenant_id, || async {
                core.run_memory_maintenance().await
            })
            .await
            .map_err(|e| e.to_string())?;
            store
                .reset_assistant_observe_streak()
                .await
                .map_err(|e| e.to_string())?;
            let settings = store
                .get_assistant_global_settings()
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true, "settings": settings, "report": report }))
        }
        "listAssistantMemories" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let limit = params.get("limit").and_then(|v| v.as_i64()).unwrap_or(100);
            let filter = seven_chat_agent_core::store::memory::ListMemoryFilter {
                tier: params
                    .get("tier")
                    .and_then(|v| v.as_str())
                    .map(String::from),
                status: params
                    .get("status")
                    .and_then(|v| v.as_str())
                    .map(String::from),
                scope: params
                    .get("scope")
                    .and_then(|v| v.as_str())
                    .map(String::from),
                category: params
                    .get("category")
                    .and_then(|v| v.as_str())
                    .map(String::from),
            };
            let memories = store
                .list_memories_filtered(friend_id, filter, limit)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "memories": memories }))
        }
        "getAssistantMemoryStats" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let stats = store
                .memory_stats(friend_id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "stats": stats }))
        }
        "previewAssistantMemoryRecall" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let prompt = params
                .get("prompt")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let limit = params.get("limit").and_then(|v| v.as_i64()).unwrap_or(8);
            let workspace_id = if let Some(w) = params.get("workspace_id").and_then(|v| v.as_str()) {
                Some(w.to_string())
            } else {
                store
                    .get_active_workspace(friend_id)
                    .await
                    .ok()
                    .flatten()
                    .map(|w| w.id)
            };
            let ctx = seven_chat_agent_core::memory_tier::RecallContext {
                conversation_id: params
                    .get("conversation_id")
                    .and_then(|v| v.as_str())
                    .map(String::from),
                friend_id: params
                    .get("friend_id")
                    .and_then(|v| v.as_str())
                    .map(String::from),
                workspace_id,
            };
            let memories = store
                .recall_memories_for_turn(friend_id, &prompt, limit, false, &ctx)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "memories": memories, "prompt": prompt }))
        }
        "patchAssistantMemory" => {
            let memory_id = params
                .get("memory_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "memory_id required".to_string())?;
            let kind = params.get("kind").and_then(|v| v.as_str());
            let content = params.get("content").and_then(|v| v.as_str());
            let weight = params.get("weight").and_then(|v| v.as_f64());
            let pinned = params.get("pinned").and_then(|v| v.as_bool());
            let tier = params.get("tier").and_then(|v| v.as_str());
            let scope = params.get("scope").and_then(|v| v.as_str());
            let scope_ref = params.get("scope_ref").and_then(|v| v.as_str());
            let importance = params.get("importance").and_then(|v| v.as_i64()).map(|v| v as i32);
            let status = params.get("status").and_then(|v| v.as_str());
            let title = params.get("title").and_then(|v| v.as_str());
            let summary = params.get("summary").and_then(|v| v.as_str());
            let promote = params
                .get("promote_to_curated")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let memory = store
                .update_memory(
                    memory_id,
                    kind,
                    content,
                    weight,
                    pinned,
                    tier,
                    scope,
                    scope_ref.map(Some),
                    importance,
                    status,
                    title.map(Some),
                    summary.map(Some),
                    promote,
                )
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "memory": memory }))
        }
        "listAssistantSkills" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let skills = store
                .list_skills(friend_id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "skills": skills }))
        }
        "listAssistantReflections" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let reflections = store
                .list_reflections(friend_id, 50)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "reflections": reflections }))
        }
        "listAssistantTodos" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let status = params
                .get("status")
                .and_then(|v| v.as_str())
                .map(seven_chat_agent_core::domain::AssistantTodoStatus::parse);
            let limit = params.get("limit").and_then(|v| v.as_i64()).unwrap_or(200);
            let todos = store
                .list_assistant_todos(friend_id, status, limit)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "todos": todos }))
        }
        "createAssistantTodo" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let title = params
                .get("title")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "title required".to_string())?;
            let detail = params.get("detail").and_then(|v| v.as_str());
            let priority = params.get("priority").and_then(|v| v.as_i64()).unwrap_or(1);
            let remind_after_seconds = params
                .get("remind_after_seconds")
                .and_then(|v| v.as_i64());
            let raw_text = params.get("raw_text").and_then(|v| v.as_str());
            let intent = if let Some(raw) = raw_text {
                seven_chat_agent_core::assistant_intent::parse_quick_intent(raw).unwrap_or(
                    seven_chat_agent_core::assistant_intent::AssistantIntent::TodoCreate {
                        title: title.to_string(),
                        detail: detail.map(str::to_string),
                        priority,
                        remind_after_seconds,
                    },
                )
            } else {
                seven_chat_agent_core::assistant_intent::AssistantIntent::TodoCreate {
                    title: title.to_string(),
                    detail: detail.map(str::to_string),
                    priority,
                    remind_after_seconds,
                }
            };
            let plan = seven_chat_agent_core::assistant_task_planner::plan_from_intent(friend_id, intent);
            let todo = core
                .execute_assistant_task_plan(friend_id, &plan)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "planner created no todo".to_string())?;
            Ok(serde_json::json!({ "todo": todo }))
        }
        "updateAssistantTodo" => {
            let todo_id = params
                .get("todo_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "todo_id required".to_string())?;
            let title = params
                .get("title")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "title required".to_string())?;
            let detail = params.get("detail").and_then(|v| v.as_str());
            let priority = params.get("priority").and_then(|v| v.as_i64()).unwrap_or(1);
            let status = params
                .get("status")
                .and_then(|v| v.as_str())
                .map(seven_chat_agent_core::domain::AssistantTodoStatus::parse);
            let todo = store
                .update_assistant_todo(todo_id, title, detail, priority, status)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "todo not found".to_string())?;
            Ok(serde_json::json!({ "todo": todo }))
        }
        "runAssistantTodosOnce" => {
            core.enqueue_assistant_task(seven_chat_agent_core::AssistantQueueTask::IdleTick)
                .await
                .map_err(|e| e.to_string())?;
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let todos = store
                .list_assistant_todos(friend_id, None, 200)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true, "queued": true, "todos": todos }))
        }
        "listAssistantQueueJobs" => {
            let status = params.get("status").and_then(|v| v.as_str());
            let limit = params.get("limit").and_then(|v| v.as_i64()).unwrap_or(200);
            let jobs = store
                .list_assistant_queue_jobs(status, limit)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "jobs": jobs }))
        }
        "getAssistantQueueStats" => {
            let stats = store
                .assistant_queue_stats()
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "stats": stats }))
        }
        "replayFailedAssistantQueueJobs" => {
            let limit = params.get("limit").and_then(|v| v.as_i64()).unwrap_or(100);
            let replayed = store
                .replay_failed_assistant_jobs(limit)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true, "replayed": replayed }))
        }
        "listInvites" => {
            let friend_id = params.get("friend_id").and_then(|v| v.as_str());
            if let Some(fid) = friend_id {
                let invites = store.list_invites(fid).await.map_err(|e| e.to_string())?;
                return Ok(serde_json::json!({ "invites": invites }));
            }
            let friends = store.list_friends().await.map_err(|e| e.to_string())?;
            let mut all = Vec::new();
            for f in friends {
                if f.backend_kind == seven_chat_agent_core::domain::BackendKind::Human {
                    let invites = store
                        .list_invites(&f.id)
                        .await
                        .map_err(|e| e.to_string())?;
                    all.extend(invites);
                }
            }
            Ok(serde_json::json!({ "invites": all }))
        }
        "createInvite" => {
            let friend_id = params
                .get("friend_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "friend_id required".to_string())?;
            let expires_in_hours = params
                .get("expires_in_hours")
                .and_then(|v| v.as_i64())
                .unwrap_or(72);
            let invite = store
                .create_invite(friend_id, expires_in_hours)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "invite": invite }))
        }
        "deleteInvite" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            store.delete_invite(id).await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true }))
        }
        "humanState" => {
            let code = params
                .get("code")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "code required".to_string())?;
            let invite = store
                .get_invite_by_code(code)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "invite not found".to_string())?;
            if invite.used_at.is_none() {
                let _ = store.consume_invite(code).await;
            }
            let friend = store
                .get_friend(&invite.friend_id)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "friend not found".to_string())?;
            let session = store
                .upsert_human_session(&friend.id, "invite", None)
                .await
                .map_err(|e| e.to_string())?;
            let convs = store.list_conversations().await.map_err(|e| e.to_string())?;
            let messages = if let Some(c) = convs.iter().find(|c| c.target_id == friend.id) {
                store
                    .list_messages(&c.id, 200)
                    .await
                    .map_err(|e| e.to_string())?
            } else {
                Vec::new()
            };
            Ok(serde_json::json!({
                "friend": friend,
                "session": session,
                "messages": messages,
            }))
        }
        "humanSend" => {
            let code = params
                .get("code")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "code required".to_string())?;
            let content = params
                .get("content")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "content required".to_string())?;
            let conversation_id = params.get("conversation_id").and_then(|v| v.as_str());
            let invite = store
                .get_invite_by_code(code)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "invite not found".to_string())?;
            let friend_id = invite.friend_id.clone();
            let conv_id = if let Some(cid) = conversation_id {
                cid.to_string()
            } else {
                store
                    .get_or_create_dm(&friend_id)
                    .await
                    .map_err(|e| e.to_string())?
                    .id
            };
            core.dispatcher
                .send_human_message(&conv_id, &friend_id, content)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true, "conversation_id": conv_id }))
        }
        "humanTyping" => {
            let code = params
                .get("code")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "code required".to_string())?;
            let duration_ms = params
                .get("duration_ms")
                .and_then(|v| v.as_i64())
                .unwrap_or(3000);
            let invite = store
                .get_invite_by_code(code)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "invite not found".to_string())?;
            store
                .set_human_typing(&invite.friend_id, duration_ms)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true }))
        }
        "createCliRelayPairingToken" => {
            let token = core.cli_relay.create_pairing_token();
            let bind = seven_chat_agent_core::env::var_or(
                "SEVEN_CHAT_AGENT_BIND",
                "HONEYCOMB_BIND",
                "127.0.0.1:18737",
            );
            let relay_ws_url = format!("ws://{bind}/cli-relay");
            Ok(serde_json::json!({
                "pairing_token": token,
                "relay_ws_url": relay_ws_url,
            }))
        }
        "listCliRelays" => {
            let relays = core.cli_relay.list_nodes();
            Ok(serde_json::json!({ "relays": relays }))
        }
        "previewTenantInvite" => {
            let code = params
                .get("code")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "code required".to_string())?;
            let preview = store.preview_tenant_invite(code).await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "preview": preview }))
        }
        "listTenantMembers" => {
            let members = store
                .list_users_in_tenant(store.tenant_id())
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "members": members, "tenant_id": store.tenant_id() }))
        }
        "listTenantInvites" => {
            ws_require_admin(&params, &store).await?;
            let invites = store
                .list_tenant_invites(store.tenant_id())
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "invites": invites }))
        }
        "createTenantInvite" => {
            let session = ws_require_admin(&params, &store).await?;
            let invited_email = params.get("invited_email").and_then(|v| v.as_str());
            let role = params.get("role").and_then(|v| v.as_str());
            let expires_in_hours = params
                .get("expires_in_hours")
                .and_then(|v| v.as_i64())
                .unwrap_or(168);
            let invite = store
                .create_tenant_invite(
                    store.tenant_id(),
                    &session.user_id,
                    invited_email,
                    role,
                    expires_in_hours,
                )
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "invite": invite }))
        }
        "deleteTenantInvite" => {
            ws_require_admin(&params, &store).await?;
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            store
                .delete_tenant_invite(store.tenant_id(), id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true }))
        }
        "updateTenantMemberRole" => {
            ws_require_admin(&params, &store).await?;
            let user_id = params
                .get("user_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "user_id required".to_string())?;
            let role = params
                .get("role")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "role required".to_string())?;
            let user = store
                .update_user_role_in_tenant(store.tenant_id(), user_id, role)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "user": user }))
        }
        "getAgentDna" => {
            let dna = store.get_agent_dna().await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "dna": dna }))
        }
        "previewAgentDna" => {
            let dna = store.get_agent_dna().await.map_err(|e| e.to_string())?;
            let rendered = seven_chat_agent_core::agent_dna::render_dna_block(&dna);
            Ok(serde_json::json!({ "dna": dna, "rendered": rendered }))
        }
        "upsertAgentDna" => {
            ws_require_admin(&params, &store).await?;
            let body: seven_chat_agent_core::agent_dna::AgentDna =
                serde_json::from_value(params).map_err(|e| e.to_string())?;
            let dna = store.upsert_agent_dna(body).await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "dna": dna }))
        }
        _ => Err(format!("unsupported method: {method}")),
    }
}

async fn ws_require_admin(
    params: &serde_json::Value,
    store: &seven_chat_agent_core::store::SqliteStore,
) -> std::result::Result<seven_chat_agent_core::domain::AuthSession, String> {
    let token = params
        .get("auth_token")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .ok_or_else(|| "auth_token required".to_string())?;
    let session = store
        .resolve_session(token)
        .await
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "invalid session".to_string())?;
    if session.role != "admin" {
        return Err("需要管理员权限".into());
    }
    Ok(session)
}

async fn resolve_tenant_store(
    state: &AppState,
    params: &serde_json::Value,
) -> std::result::Result<seven_chat_agent_core::store::SqliteStore, String> {
    if let Some(token) = params
        .get("auth_token")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
    {
        if let Some(session) = state
            .core
            .store
            .resolve_session(token)
            .await
            .map_err(|e| e.to_string())?
        {
            return Ok(
                state
                    .core
                    .store
                    .for_tenant(&session.tenant_id)
                    .for_user(&session.user_id),
            );
        }
    }
    if seven_chat_agent_core::auth::auth_required() {
        return Err("需要登录（传 auth_token）".into());
    }
    Ok(state.core.store.as_ref().clone())
}

async fn group_bundle_json(
    store: &seven_chat_agent_core::store::SqliteStore,
    providers: &seven_chat_agent_core::provider::ProviderRegistry,
    g: &seven_chat_agent_core::domain::Group,
) -> std::result::Result<serde_json::Value, String> {
    let members = store
        .list_group_member_configs(&g.id)
        .await
        .map_err(|e| e.to_string())?;
    let member_ids: Vec<String> = members.iter().map(|m| m.friend_id.clone()).collect();
    let expert_member_ids: Vec<String> = store
        .list_group_expert_friend_ids(&g.id)
        .await
        .map_err(|e| e.to_string())?;
    let assistant_member_id = store
        .group_assistant_member_id(&g.id)
        .await
        .map_err(|e| e.to_string())?;
    let workspaces = store
        .list_group_workspaces(&g.id)
        .await
        .map_err(|e| e.to_string())?;
    let member_bindings = store
        .list_group_member_bindings(&g.id)
        .await
        .map_err(|e| e.to_string())?;
    let task_flow_readiness = validate_group_task_flow_readiness(
        store,
        providers,
        &g.settings,
        &expert_member_ids,
    )
    .await
    .map_err(|e| e.to_string())?;
    let assistant_resolved = store
        .resolve_group_assistant_settings(&g.settings.assistant)
        .await
        .map_err(|e| e.to_string())?;
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
