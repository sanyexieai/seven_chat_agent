use std::sync::Arc;

use crate::agent::assistant::skills::SkillLibrary;
use crate::domain::{Friend, Message, SenderKind};
use crate::store::memory::NewMemory;
use crate::store::SqliteStore;
use crate::{Error, Result};

use super::config::RuntimeProfile;

pub struct MemoryService {
    store: Arc<SqliteStore>,
    skills_dir: String,
}

impl MemoryService {
    pub fn new(store: Arc<SqliteStore>, skills_dir: impl Into<String>) -> Self {
        Self {
            store,
            skills_dir: skills_dir.into(),
        }
    }

    pub async fn build_system_prompt(
        &self,
        friend: &Friend,
        profile: &RuntimeProfile,
        prompt: &str,
        extra_group: Option<&str>,
        recall_ctx: &crate::memory_tier::RecallContext,
    ) -> Result<String> {
        use super::config::InferenceBackend;
        let mut s = friend.system_prompt.clone();
        if !friend.focus_tags.is_empty() {
            s.push_str("\n\n关注点：");
            s.push_str(&friend.focus_tags.join("、"));
        }
        if let Some(per) = &friend.personality {
            s.push_str("\n性格：");
            s.push_str(per);
        }
        s.push_str(&format!(
            "\n\n你的名字是「{}」。请用第一人称、自然的中文聊天风格回答。",
            friend.name
        ));

        match &profile.inference {
            InferenceBackend::WorkerBee(w) => {
                s.push_str(&format!(
                    "\n\n（推理模型：{}/{}）",
                    w.provider.provider_id, w.provider.model
                ));
            }
            InferenceBackend::ExternalCli(c) => {
                let cli_name = match c.preset.as_str() {
                    "codex-exec" => "Codex CLI",
                    _ => c.cmd.as_deref().unwrap_or(&c.preset),
                };
                s.push_str(&format!("\n\n（本机外部 CLI：{cli_name}，不经平台 API）"));
            }
        }

        let memories = self
            .store
            .recall_memories_for_turn(
                &friend.id,
                prompt,
                profile.memory_top_k as i64,
                true,
                recall_ctx,
            )
            .await
            .unwrap_or_default();
        if !memories.is_empty() {
            s.push_str("\n\n[助理整理记忆 · 仅 curated 层]");
            for m in &memories {
                s.push_str("\n- ");
                s.push_str(&crate::memory_tier::prompt_line(
                    &m.scope,
                    &m.kind,
                    m.importance,
                    m.summary.as_deref(),
                    &m.content,
                ));
            }
        }

        let mut lib = SkillLibrary::new(&self.skills_dir, friend.id.clone());
        lib.reload();
        let skills = lib.tier1_index(&prompt.to_lowercase());
        if !skills.is_empty() {
            s.push_str("\n\n[可用技能 Tier 1]");
            for sk in &skills {
                s.push_str(&format!("\n- {}: {}", sk.name, sk.summary));
            }
        }

        if let Some(extra) = extra_group {
            if !extra.trim().is_empty() {
                s.push_str("\n\n[群规]\n");
                s.push_str(extra);
            }
        }

        Ok(s)
    }

    pub fn build_messages(
        &self,
        friend: &Friend,
        ctx: &crate::agent::ChatContext,
        system: String,
        prompt: &str,
        vision: bool,
    ) -> Vec<crate::provider::types::ChatMessage> {
        use crate::attachment::build_chat_content;
        use crate::provider::types::ChatMessage;
        let data_dir = std::env::var("SEVEN_CHAT_AGENT_DATA").unwrap_or_else(|_| "data".into());
        let history = &ctx.history;
        let mut msgs = vec![ChatMessage::system(system)];
        let take = history.len();
        for (idx, m) in history.iter().enumerate() {
            if idx + 1 == take {
                break;
            }
            let role = match m.sender_kind {
                SenderKind::User => "user",
                SenderKind::Friend => {
                    if m.sender_id == friend.id {
                        "assistant"
                    } else {
                        "user"
                    }
                }
                SenderKind::System => "system",
            };
            let text = match m.sender_kind {
                SenderKind::Friend if m.sender_id != friend.id => {
                    format!("[{}]: {}", m.sender_name, m.content)
                }
                _ => m.content.clone(),
            };
            let content = if m.attachments.is_empty() {
                serde_json::Value::String(text)
            } else {
                build_chat_content(
                    &data_dir,
                    &ctx.conversation_id,
                    &text,
                    &m.attachments,
                    vision,
                )
            };
            msgs.push(ChatMessage {
                role: role.into(),
                content,
                name: None,
            });
        }
        let final_content = build_chat_content(
            &data_dir,
            &ctx.conversation_id,
            prompt,
            &ctx.user_attachments,
            vision,
        );
        msgs.push(ChatMessage::user_value(final_content));
        msgs
    }

    pub async fn post_turn(
        &self,
        friend_id: &str,
        conversation_id: &str,
        turn_id: &str,
        prompt: &str,
        response: &str,
        tokens_in: i64,
        tokens_out: i64,
        provider_id: &str,
        model: &str,
        api_key_id: Option<&str>,
        providers: &crate::provider::ProviderRegistry,
    ) {
        let mut global = self
            .store
            .get_assistant_global_settings()
            .await
            .unwrap_or_default();
        let is_builtin = self
            .store
            .builtin_assistant_id()
            .await
            .ok()
            .flatten()
            .is_some_and(|id| id == friend_id);
        let used_tokens = (tokens_in.max(0) + tokens_out.max(0)) as u64;
        if let Ok(updated) = self.store.consume_assistant_tokens(used_tokens).await {
            global = updated;
        }

        if is_builtin
            && global.observe_enabled
            && crate::memory_record_policy::evaluate_assist_memo(prompt, response, &global)
                .should_record()
        {
            let summary = format!(
                "[协助记录]\n用户：{}\n助理：{}",
                crate::assistant_accumulation::truncate_chars(prompt, 280),
                crate::assistant_accumulation::truncate_chars(response, 400),
            );
            if let Err(e) = self
                .store
                .insert_memory(NewMemory {
                    owner_friend_id: friend_id.to_string(),
                    kind: crate::assistant_accumulation::MEMORY_KIND_MEMO.to_string(),
                    content: summary,
                    source_message_id: None,
                    weight: 0.5,
                    pinned: false,
                    tier: crate::memory_tier::TIER_RAW.to_string(),
                    scope: crate::memory_tier::SCOPE_CONVERSATION.to_string(),
                    scope_ref: Some(conversation_id.to_string()),
                    importance: 0,
                    status: crate::memory_tier::STATUS_ACTIVE.to_string(),
                    title: None,
                    summary: None,
                    expires_at: None,
                    workspace_id: None,
                })
                .await
            {
                tracing::warn!(err = %e, "runtime.session_memo failed");
            }
        }
        let budget_ok = self.store.assistant_budget_available(&global);
        if !budget_ok {
            tracing::info!(
                used = global.monthly_tokens_used,
                budget = global.monthly_token_budget,
                "assistant monthly token budget exhausted, skip proactive work"
            );
            return;
        }

        if global.auto_extract_memories {
            if let Err(e) = self
                .extract_memories(
                    friend_id,
                    prompt,
                    response,
                    provider_id,
                    model,
                    api_key_id,
                    providers,
                )
                .await
            {
                tracing::warn!(err = %e, "runtime.extract_memories failed");
            }
        }
        if global.evolution_enabled {
            if let Err(e) = self
                .reflect(
                    friend_id,
                    turn_id,
                    prompt,
                    response,
                    provider_id,
                    model,
                    api_key_id,
                    providers,
                )
                .await
            {
                tracing::warn!(err = %e, "runtime.reflect failed");
            }
        }
        if global.auto_consolidate {
            if is_builtin {
                let _ = self
                    .store
                    .touch_observe_consolidate(friend_id, &global)
                    .await;
            } else if let Err(e) = self.store.consolidate_memories(friend_id).await {
                tracing::warn!(err = %e, "runtime.consolidate_memories failed");
            }
        }

        if is_builtin {
            let _ = self
                .store
                .create_assistant_todo(
                    friend_id,
                    "整理本轮知识沉淀",
                    Some("检查本轮的备忘录/知识/工具是否已更新"),
                    None,
                    None,
                    2,
                    Some(turn_id),
                )
                .await;
            if let Ok(Some(dir)) = self.store.builtin_assistant_skills_dir().await {
                if let Err(e) = self.store.sync_skills_from_disk(friend_id, &dir).await {
                    tracing::debug!(err = %e, "runtime.sync_skills_from_disk failed");
                }
            }
        }
    }

    async fn extract_memories(
        &self,
        friend_id: &str,
        prompt: &str,
        response: &str,
        provider_id: &str,
        model: &str,
        api_key_id: Option<&str>,
        providers: &crate::provider::ProviderRegistry,
    ) -> Result<()> {
        use crate::provider::types::{ChatMessage, ProviderEvent};
        use futures::StreamExt;

        let provider = providers
            .get(provider_id)
            .ok_or_else(|| Error::provider(format!("provider missing: {provider_id}")))?;
        let mut req = crate::provider::types::ChatRequest::new(
            model,
            vec![
                ChatMessage::system(&format!(
                    "从助理帮助用户的对话中抽取可复用知识。只输出 JSON 数组，每项含 kind(knowledge)、content、weight(0~1)、scope(global|user|friend|conversation|ephemeral)、scope_ref(可选id；user 偏好请用 \"{}\"）、importance(0-3)、title、summary。若无稳定可复用新事实，输出 []。",
                    self.store.tenant_id()
                )),
                ChatMessage::user(format!(
                    "用户：\n{prompt}\n\n助理：\n{response}\n\n最多 4 条；无新事实则 []。"
                )),
            ],
        );
        req.api_key_id = api_key_id.map(String::from);
        req.stream = false;
        req.response_format_json = true;
        let mut stream = provider.chat(req).await?;
        let mut raw = String::new();
        while let Some(item) = stream.next().await {
            if let Ok(ProviderEvent::Token(t)) = item {
                raw.push_str(&t);
            }
        }
        let json = crate::llm_json::extract_json_array(&raw).unwrap_or(raw);
        let parsed: serde_json::Value = match serde_json::from_str(&json) {
            Ok(v) => v,
            Err(_) => return Ok(()),
        };
        if let Some(arr) = parsed.as_array() {
            for item in arr {
                let kind =
                    crate::assistant_accumulation::MEMORY_KIND_KNOWLEDGE.to_string();
                let content = item
                    .get("content")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .trim()
                    .to_string();
                if content.is_empty() {
                    continue;
                }
                let weight = item
                    .get("weight")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.5)
                    .clamp(0.0, 1.0);
                let scope = item
                    .get("scope")
                    .and_then(|v| v.as_str())
                    .unwrap_or(crate::memory_tier::SCOPE_GLOBAL);
                let scope_ref = item
                    .get("scope_ref")
                    .and_then(|v| v.as_str())
                    .map(String::from);
                let importance = item
                    .get("importance")
                    .and_then(|v| v.as_i64())
                    .unwrap_or(crate::memory_tier::importance_from_weight(weight) as i64)
                    as i32;
                let title = item
                    .get("title")
                    .and_then(|v| v.as_str())
                    .map(String::from);
                let summary = item
                    .get("summary")
                    .and_then(|v| v.as_str())
                    .map(String::from)
                    .or_else(|| Some(crate::memory_tier::make_summary(&content, 240)));
                let _ = self
                    .store
                    .insert_memory(NewMemory {
                        owner_friend_id: friend_id.to_string(),
                        kind,
                        content: content.clone(),
                        source_message_id: None,
                        weight,
                        pinned: false,
                        tier: crate::memory_tier::TIER_CURATED.to_string(),
                        scope: scope.to_string(),
                        scope_ref,
                        importance,
                        status: crate::memory_tier::STATUS_ACTIVE.to_string(),
                        title,
                        summary,
                        expires_at: None,
                        workspace_id: None,
                    })
                    .await;
            }
        }
        Ok(())
    }

    async fn reflect(
        &self,
        friend_id: &str,
        turn_id: &str,
        prompt: &str,
        response: &str,
        provider_id: &str,
        model: &str,
        api_key_id: Option<&str>,
        providers: &crate::provider::ProviderRegistry,
    ) -> Result<()> {
        use crate::provider::types::{ChatMessage, ProviderEvent};
        use futures::StreamExt;

        let provider = providers
            .get(provider_id)
            .ok_or_else(|| Error::provider(format!("provider missing: {provider_id}")))?;
        let mut req = crate::provider::types::ChatRequest::new(
            model,
            vec![
                ChatMessage::system(
                    "输出 JSON：{\"score\":0.8,\"summary\":\"...\",\"lessons\":[\"...\"]}",
                ),
                ChatMessage::user(format!("用户：\n{prompt}\n\n助理：\n{response}")),
            ],
        );
        req.api_key_id = api_key_id.map(String::from);
        req.stream = false;
        req.response_format_json = true;
        let mut stream = provider.chat(req).await?;
        let mut raw = String::new();
        while let Some(item) = stream.next().await {
            if let Ok(ProviderEvent::Token(t)) = item {
                raw.push_str(&t);
            }
        }
        let json = crate::llm_json::extract_json_object(&raw).unwrap_or(raw);
        let v: serde_json::Value = match serde_json::from_str(&json) {
            Ok(v) => v,
            Err(_) => return Ok(()),
        };
        let score = v.get("score").and_then(|v| v.as_f64()).unwrap_or(0.5);
        let summary = v
            .get("summary")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let lessons: Vec<String> = v
            .get("lessons")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|x| x.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default();
        self.store
            .insert_reflection(friend_id, turn_id, score, &summary, &lessons)
            .await?;
        for lesson in lessons {
            let lesson = lesson.trim();
            if lesson.is_empty() {
                continue;
            }
                let content = lesson.to_string();
                let _ = self
                    .store
                    .insert_memory(NewMemory {
                        owner_friend_id: friend_id.to_string(),
                        kind: crate::assistant_accumulation::MEMORY_KIND_KNOWLEDGE.to_string(),
                        content: content.clone(),
                        source_message_id: None,
                        weight: 0.65,
                        pinned: false,
                        tier: crate::memory_tier::TIER_CURATED.to_string(),
                        scope: crate::memory_tier::SCOPE_GLOBAL.to_string(),
                        scope_ref: None,
                        importance: 2,
                        status: crate::memory_tier::STATUS_ACTIVE.to_string(),
                        title: None,
                        summary: Some(crate::memory_tier::make_summary(&content, 200)),
                        expires_at: None,
                        workspace_id: None,
                    })
                    .await;
        }
        Ok(())
    }
}

fn extract_json_object(s: &str) -> Option<String> {
    let start = s.find('{')?;
    let mut depth = 0i32;
    for (i, c) in s[start..].char_indices() {
        match c {
            '{' => depth += 1,
            '}' => {
                depth -= 1;
                if depth == 0 {
                    return Some(s[start..start + i + 1].to_string());
                }
            }
            _ => {}
        }
    }
    None
}
