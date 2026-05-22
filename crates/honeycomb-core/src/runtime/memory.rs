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
            .search_memories(&friend.id, prompt, profile.memory_top_k as i64)
            .await
            .unwrap_or_default();
        if !memories.is_empty() {
            s.push_str("\n\n[长期记忆 Top-K]");
            for m in &memories {
                s.push_str(&format!("\n- ({} | w={:.1}) {}", m.kind, m.weight, m.content));
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
        system: String,
        history: &[Message],
        prompt: &str,
    ) -> Vec<crate::provider::types::ChatMessage> {
        use crate::provider::types::ChatMessage;
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
            let content = match m.sender_kind {
                SenderKind::Friend if m.sender_id != friend.id => {
                    format!("[{}]: {}", m.sender_name, m.content)
                }
                _ => m.content.clone(),
            };
            msgs.push(ChatMessage {
                role: role.into(),
                content,
                name: None,
            });
        }
        msgs.push(ChatMessage::user(prompt.to_string()));
        msgs
    }

    pub async fn post_turn(
        &self,
        friend_id: &str,
        turn_id: &str,
        prompt: &str,
        response: &str,
        provider_id: &str,
        model: &str,
        api_key_id: Option<&str>,
        providers: &crate::provider::ProviderRegistry,
    ) {
        if let Err(e) = self
            .extract_memories(friend_id, prompt, response, provider_id, model, api_key_id, providers)
            .await
        {
            tracing::warn!(err = %e, "runtime.extract_memories failed");
        }
        if let Err(e) = self
            .reflect(friend_id, turn_id, prompt, response, provider_id, model, api_key_id, providers)
            .await
        {
            tracing::warn!(err = %e, "runtime.reflect failed");
        }
        if let Err(e) = self.store.consolidate_memories(friend_id).await {
            tracing::warn!(err = %e, "runtime.consolidate_memories failed");
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
                ChatMessage::system(
                    "从对话中抽取稳定事实。只输出 JSON 数组，每项含 kind(fact|preference|project|relation|lesson), content, weight(0~1)。",
                ),
                ChatMessage::user(format!(
                    "用户：\n{prompt}\n\n助理：\n{response}\n\n最多 4 条。"
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
        let json = extract_json_array(&raw).unwrap_or(raw);
        let parsed: serde_json::Value = match serde_json::from_str(&json) {
            Ok(v) => v,
            Err(_) => return Ok(()),
        };
        if let Some(arr) = parsed.as_array() {
            for item in arr {
                let kind = item
                    .get("kind")
                    .and_then(|v| v.as_str())
                    .unwrap_or("fact")
                    .to_string();
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
                let _ = self
                    .store
                    .insert_memory(NewMemory {
                        owner_friend_id: friend_id.to_string(),
                        kind,
                        content,
                        source_message_id: None,
                        weight,
                        pinned: false,
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
        let json = extract_json_object(&raw).unwrap_or(raw);
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
        Ok(())
    }
}

fn extract_json_array(s: &str) -> Option<String> {
    let start = s.find('[')?;
    let mut depth = 0i32;
    for (i, c) in s[start..].char_indices() {
        match c {
            '[' => depth += 1,
            ']' => {
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
