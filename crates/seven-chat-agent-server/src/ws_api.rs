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
    match method {
        "health" => Ok(serde_json::json!({ "ok": true })),
        "listFriends" => {
            let friends = core.store.list_friends().await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "friends": friends }))
        }
        "getFriend" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            let friend = core
                .store
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
                .full_status(&core.store, id)
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
                .start(&core.store, id)
                .await
                .map_err(|e| e.to_string())?;
            let cli_auth = core
                .cli_oauth
                .full_status(&core.store, id)
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
                .full_status(&core.store, id)
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
                .logout(&core.store, id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "cli_auth": cli_auth }))
        }
        "upsertFriend" => {
            let req: UpsertFriend = serde_json::from_value(params).map_err(|e| e.to_string())?;
            let friend = core.store.upsert_friend(req).await.map_err(|e| e.to_string())?;
            core.agents.invalidate(&friend.id);
            Ok(serde_json::json!({ "friend": friend }))
        }
        "deleteFriend" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            core.store.delete_friend(id).await.map_err(|e| e.to_string())?;
            core.agents.invalidate(id);
            Ok(serde_json::json!({ "ok": true }))
        }
        "listGroups" => {
            let groups = core.store.list_groups().await.map_err(|e| e.to_string())?;
            let mut out = Vec::new();
            for g in &groups {
                out.push(group_bundle_json(core, g).await.map_err(|e| e.to_string())?);
            }
            Ok(serde_json::json!({ "groups": out }))
        }
        "getGroup" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            let g = core
                .store
                .get_group(id)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "group not found".to_string())?;
            let mut bundle = group_bundle_json(core, &g).await.map_err(|e| e.to_string())?;
            let conv = core
                .store
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
                &core.store,
                &core.providers,
                &req.settings,
                &expert_ids,
            )
            .await
            .map_err(|e| e.to_string())?;
            if !readiness.errors.is_empty() {
                return Err(readiness.errors.join("；"));
            }
            let g = core.store.upsert_group(req).await.map_err(|e| e.to_string())?;
            let mut bundle = group_bundle_json(core, &g).await.map_err(|e| e.to_string())?;
            let conv = core
                .store
                .get_or_create_group_conversation(&g.id)
                .await
                .map_err(|e| e.to_string())?;
            bundle["conversation_id"] = serde_json::json!(conv.id);
            Ok(bundle)
        }
        "listProviders" => {
            let providers = core.store.list_providers().await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "providers": providers }))
        }
        "upsertProvider" => {
            let req = params;
            let id = req
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "provider id required".to_string())?;
            let existing = core
                .store
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
            core.store
                .upsert_provider(&provider)
                .await
                .map_err(|e| e.to_string())?;
            core.providers.reload().await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "provider": provider }))
        }
        "deleteProvider" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            core.store.delete_provider(id).await.map_err(|e| e.to_string())?;
            core.providers.reload().await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true }))
        }
        "upsertProviderKey" => {
            let req: UpsertProviderKey =
                serde_json::from_value(params).map_err(|e| e.to_string())?;
            let provider_key = core
                .store
                .upsert_provider_key(req)
                .await
                .map_err(|e| e.to_string())?;
            core.providers.reload().await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "provider_key": provider_key }))
        }
        "deleteProviderKey" => {
            let id = params
                .get("id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "id required".to_string())?;
            core.store
                .delete_provider_key(id)
                .await
                .map_err(|e| e.to_string())?;
            core.providers.reload().await.map_err(|e| e.to_string())?;
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
            let templates = core
                .store
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
            let memory = core.store.insert_memory(body).await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "memory": memory }))
        }
        "deleteAssistantMemory" => {
            let memory_id = params
                .get("memory_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "memory_id required".to_string())?;
            core.store
                .delete_memory(memory_id)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true }))
        }
        "listProviderKeys" => {
            let provider_id = params.get("provider_id").and_then(|v| v.as_str());
            let provider_keys = core
                .store
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
            let conversation = core
                .store
                .get_or_create_dm(friend_id)
                .await
                .map_err(|e| e.to_string())?;
            let messages = core
                .store
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
                .ok_or_else(|| "content required".to_string())?;
            let conv = core
                .store
                .get_or_create_dm(friend_id)
                .await
                .map_err(|e| e.to_string())?;
            core.dispatcher
                .send_user_message(&conv.id, content)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true, "conversation_id": conv.id }))
        }
        "listConversationMessages" => {
            let id = params
                .get("conversation_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "conversation_id required".to_string())?;
            let messages = core
                .store
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
                .ok_or_else(|| "content required".to_string())?;
            core.dispatcher
                .send_user_message(id, content)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true, "conversation_id": id }))
        }
        "getAssistantGlobalSettings" => {
            let settings = core
                .store
                .get_assistant_global_settings()
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "settings": settings }))
        }
        "upsertAssistantGlobalSettings" => {
            let body: seven_chat_agent_core::domain::AssistantGlobalSettings =
                serde_json::from_value(params).map_err(|e| e.to_string())?;
            let settings = core
                .store
                .upsert_assistant_global_settings(body)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "settings": settings }))
        }
        "consolidateAssistantMemories" => {
            let report = core
                .run_memory_maintenance()
                .await
                .map_err(|e| e.to_string())?;
            core.store
                .reset_assistant_observe_streak()
                .await
                .map_err(|e| e.to_string())?;
            let settings = core
                .store
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
            let memories = core
                .store
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
            let stats = core
                .store
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
            let ctx = seven_chat_agent_core::memory_tier::RecallContext {
                conversation_id: params
                    .get("conversation_id")
                    .and_then(|v| v.as_str())
                    .map(String::from),
                friend_id: params
                    .get("friend_id")
                    .and_then(|v| v.as_str())
                    .map(String::from),
            };
            let memories = core
                .store
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
            let memory = core
                .store
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
            let skills = core
                .store
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
            let reflections = core
                .store
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
            let todos = core
                .store
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
            let todo = core
                .store
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
            let todos = core
                .store
                .list_assistant_todos(friend_id, None, 200)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true, "queued": true, "todos": todos }))
        }
        "listAssistantQueueJobs" => {
            let status = params.get("status").and_then(|v| v.as_str());
            let limit = params.get("limit").and_then(|v| v.as_i64()).unwrap_or(200);
            let jobs = core
                .store
                .list_assistant_queue_jobs(status, limit)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "jobs": jobs }))
        }
        "getAssistantQueueStats" => {
            let stats = core
                .store
                .assistant_queue_stats()
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "stats": stats }))
        }
        "replayFailedAssistantQueueJobs" => {
            let limit = params.get("limit").and_then(|v| v.as_i64()).unwrap_or(100);
            let replayed = core
                .store
                .replay_failed_assistant_jobs(limit)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true, "replayed": replayed }))
        }
        "listInvites" => {
            let friend_id = params.get("friend_id").and_then(|v| v.as_str());
            if let Some(fid) = friend_id {
                let invites = core.store.list_invites(fid).await.map_err(|e| e.to_string())?;
                return Ok(serde_json::json!({ "invites": invites }));
            }
            let friends = core.store.list_friends().await.map_err(|e| e.to_string())?;
            let mut all = Vec::new();
            for f in friends {
                if f.backend_kind == seven_chat_agent_core::domain::BackendKind::Human {
                    let invites = core
                        .store
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
            let invite = core
                .store
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
            core.store.delete_invite(id).await.map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true }))
        }
        "humanState" => {
            let code = params
                .get("code")
                .and_then(|v| v.as_str())
                .ok_or_else(|| "code required".to_string())?;
            let invite = core
                .store
                .get_invite_by_code(code)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "invite not found".to_string())?;
            if invite.used_at.is_none() {
                let _ = core.store.consume_invite(code).await;
            }
            let friend = core
                .store
                .get_friend(&invite.friend_id)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "friend not found".to_string())?;
            let session = core
                .store
                .upsert_human_session(&friend.id, "invite", None)
                .await
                .map_err(|e| e.to_string())?;
            let convs = core.store.list_conversations().await.map_err(|e| e.to_string())?;
            let messages = if let Some(c) = convs.iter().find(|c| c.target_id == friend.id) {
                core.store
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
            let invite = core
                .store
                .get_invite_by_code(code)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "invite not found".to_string())?;
            let friend_id = invite.friend_id.clone();
            let conv_id = if let Some(cid) = conversation_id {
                cid.to_string()
            } else {
                core.store
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
            let invite = core
                .store
                .get_invite_by_code(code)
                .await
                .map_err(|e| e.to_string())?
                .ok_or_else(|| "invite not found".to_string())?;
            core.store
                .set_human_typing(&invite.friend_id, duration_ms)
                .await
                .map_err(|e| e.to_string())?;
            Ok(serde_json::json!({ "ok": true }))
        }
        "createCliRelayPairingToken" => {
            let token = core.cli_relay.create_pairing_token();
            Ok(serde_json::json!({ "pairing_token": token }))
        }
        "listCliRelays" => {
            let relays = core.cli_relay.list_nodes();
            Ok(serde_json::json!({ "relays": relays }))
        }
        _ => Err(format!("unsupported method: {method}")),
    }
}

async fn group_bundle_json(
    core: &seven_chat_agent_core::SevenChatAgent,
    g: &seven_chat_agent_core::domain::Group,
) -> std::result::Result<serde_json::Value, String> {
    let members = core
        .store
        .list_group_member_configs(&g.id)
        .await
        .map_err(|e| e.to_string())?;
    let member_ids: Vec<String> = members.iter().map(|m| m.friend_id.clone()).collect();
    let expert_member_ids: Vec<String> = core
        .store
        .list_group_expert_friend_ids(&g.id)
        .await
        .map_err(|e| e.to_string())?;
    let assistant_member_id = core
        .store
        .group_assistant_member_id(&g.id)
        .await
        .map_err(|e| e.to_string())?;
    let task_flow_readiness = validate_group_task_flow_readiness(
        &core.store,
        &core.providers,
        &g.settings,
        &expert_member_ids,
    )
    .await
    .map_err(|e| e.to_string())?;
    let assistant_resolved = core
        .store
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
        "task_flow_readiness": task_flow_readiness,
    }))
}
