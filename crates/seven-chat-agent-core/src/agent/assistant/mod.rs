pub mod guard;
pub mod memory;
pub mod metacog;
pub mod skills;

use std::sync::Arc;

use async_stream::stream;
use async_trait::async_trait;
use futures::stream::{BoxStream, StreamExt};
use tokio::sync::Mutex;

use crate::agent::{Agent, AgentEvent, AgentKind, ChatContext, Judgment, ProviderUsageInfo};
use crate::domain::{AssistantBackendConfig, BackendKind, Friend, Message, SenderKind};
use crate::provider::types::{ChatMessage, ChatRequest, ProviderEvent};
use crate::provider::ProviderRegistry;
use crate::store::SqliteStore;
use crate::{Error, Result};

pub use memory::AssistantMemory;
pub use skills::SkillLibrary;

pub struct AssistantAgent {
    friend: Friend,
    store: Arc<SqliteStore>,
    providers: Arc<ProviderRegistry>,
    cfg: AssistantBackendConfig,
    skills: Arc<Mutex<SkillLibrary>>,
}

impl AssistantAgent {
    pub fn new(
        friend: Friend,
        store: Arc<SqliteStore>,
        providers: Arc<ProviderRegistry>,
    ) -> Result<Self> {
        let cfg: AssistantBackendConfig = serde_json::from_value(friend.backend_config.clone())
            .map_err(|e| Error::Config(format!("invalid assistant backend_config: {e}")))?;
        let lib = SkillLibrary::new(cfg.skills_dir.clone(), friend.id.clone());
        Ok(Self {
            friend,
            store,
            providers,
            cfg,
            skills: Arc::new(Mutex::new(lib)),
        })
    }

    fn fallback_provider_id(&self) -> String {
        crate::runtime::resolve_worker_bee_provider(
            &self.cfg.provider_id,
            &self.cfg.model,
            self.cfg.api_key_id.clone(),
        )
        .provider_id
    }

    fn fallback_model(&self) -> String {
        crate::runtime::resolve_worker_bee_provider(
            &self.cfg.provider_id,
            &self.cfg.model,
            self.cfg.api_key_id.clone(),
        )
        .model
    }

    async fn build_system_prompt(&self, ctx: &ChatContext, prompt: &str) -> String {
        let mut s = self.friend.system_prompt.clone();

        let memories = self
            .store
            .search_memories(&self.friend.id, prompt, self.cfg.memory_top_k as i64)
            .await
            .unwrap_or_default();
        if !memories.is_empty() {
            s.push_str("\n\n[长期记忆 Top-K]");
            for m in &memories {
                s.push_str(&format!("\n- ({} | w={:.1}) {}", m.kind, m.weight, m.content));
            }
        }

        let lib = self.skills.lock().await;
        let lined_skills = lib.tier1_index(&prompt.to_lowercase());
        if !lined_skills.is_empty() {
            s.push_str("\n\n[可用技能 Tier 1]");
            for sk in &lined_skills {
                s.push_str(&format!("\n- {}: {}", sk.name, sk.summary));
            }
            s.push_str(
                "\n如需调用某个技能的完整步骤，请在回复里说『需要技能：<name>』；我会在下一轮补全。",
            );
        }
        if let Some(extra) = ctx
            .group_settings
            .as_ref()
            .and_then(|g| g.extra_system_prompt.clone())
        {
            if !extra.trim().is_empty() {
                s.push_str("\n\n[群规]\n");
                s.push_str(&extra);
            }
        }

        s
    }

    fn build_messages(&self, ctx: &ChatContext, system: String, prompt: &str) -> Vec<ChatMessage> {
        let mut msgs = vec![ChatMessage::system(system)];
        let take = ctx.history.len();
        for (idx, m) in ctx.history.iter().enumerate() {
            if idx + 1 == take {
                break;
            }
            let role = match m.sender_kind {
                SenderKind::User => "user",
                SenderKind::Friend => {
                    if m.sender_id == self.friend.id {
                        "assistant"
                    } else {
                        "user"
                    }
                }
                SenderKind::System => "system",
            };
            let content = match m.sender_kind {
                SenderKind::Friend if m.sender_id != self.friend.id => {
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

    async fn run_provider(
        &self,
        msgs: Vec<ChatMessage>,
        json_mode: bool,
    ) -> Result<String> {
        let provider_id = self.fallback_provider_id();
        let provider = self
            .providers
            .get(&provider_id)
            .ok_or_else(|| Error::provider(format!("assistant provider missing: {provider_id}")))?;
        let mut req = ChatRequest::new(self.fallback_model(), msgs);
        req.api_key_id = self.cfg.api_key_id.clone();
        req.stream = false;
        req.response_format_json = json_mode;
        req.temperature = Some(0.4);
        req.max_tokens = Some(800);
        let mut stream = provider.chat(req).await?;
        let mut buf = String::new();
        while let Some(item) = stream.next().await {
            match item? {
                ProviderEvent::Token(t) => buf.push_str(&t),
                ProviderEvent::Thinking(_) | ProviderEvent::Done { .. } => {}
            }
        }
        Ok(buf)
    }

    async fn extract_memories(&self, prompt: &str, response: &str) -> Result<()> {
        let msgs = vec![
            ChatMessage::system(
                "你是一个用于知识沉淀的助手。从助理帮助用户解决问题的对话中，抽出可长期复用的知识点。只输出 JSON 数组，每项含 kind（固定填 knowledge）、content、weight(0~1)。不要输出多余文字。",
            ),
            ChatMessage::user(format!(
                "用户消息：\n{prompt}\n\n助理回应：\n{response}\n\n请抽出最多 4 条结构化记忆。"
            )),
        ];
        let raw = self.run_provider(msgs, true).await?;
        let json = json_array_from(&raw).unwrap_or_else(|| raw.clone());
        let parsed: serde_json::Value = match serde_json::from_str(&json) {
            Ok(v) => v,
            Err(_) => return Ok(()),
        };
        if let Some(arr) = parsed.as_array() {
            for item in arr {
                let kind = crate::assistant_accumulation::MEMORY_KIND_KNOWLEDGE.to_string();
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
                    .insert_memory(crate::store::memory::NewMemory {
                        owner_friend_id: self.friend.id.clone(),
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

    async fn reflect(&self, turn_id: &str, prompt: &str, response: &str) -> Result<()> {
        let msgs = vec![
            ChatMessage::system("你是一个反思助手。基于一次对话给出 0~1 的自评分数（评估你的回应是否到位）和一段简短反思。只输出 JSON 形如 {\"score\":0.8,\"summary\":\"...\",\"lessons\":[\"...\"]}。"),
            ChatMessage::user(format!(
                "用户消息：\n{prompt}\n\n助理回应：\n{response}\n\n请给出反思 JSON。"
            )),
        ];
        let raw = self.run_provider(msgs, true).await?;
        let json = json_object_from(&raw).unwrap_or(raw);
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
            .insert_reflection(&self.friend.id, turn_id, score, &summary, &lessons)
            .await?;
        for lesson in lessons {
            let lesson = lesson.trim();
            if lesson.is_empty() {
                continue;
            }
            let _ = self
                .store
                .insert_memory(crate::store::memory::NewMemory {
                    owner_friend_id: self.friend.id.clone(),
                    kind: crate::assistant_accumulation::MEMORY_KIND_KNOWLEDGE.to_string(),
                    content: lesson.to_string(),
                    source_message_id: None,
                    weight: 0.65,
                    pinned: false,
                })
                .await;
        }
        Ok(())
    }
}

#[async_trait]
impl Agent for AssistantAgent {
    fn kind(&self) -> AgentKind {
        AgentKind::Assistant
    }

    async fn warmup(&self) -> Result<()> {
        let mut lib = self.skills.lock().await;
        lib.reload();
        let dir = if self.cfg.skills_dir.trim().is_empty() {
            "data/skills".to_string()
        } else {
            self.cfg.skills_dir.clone()
        };
        let _ = self
            .store
            .sync_skills_from_disk(&self.friend.id, &dir)
            .await;
        Ok(())
    }

    async fn send(
        &self,
        ctx: ChatContext,
        prompt: String,
    ) -> Result<BoxStream<'static, AgentEvent>> {
        let system = self.build_system_prompt(&ctx, &prompt).await;
        let messages = self.build_messages(&ctx, system, &prompt);
        let provider_id = self.fallback_provider_id();
        let provider = self
            .providers
            .get(&provider_id)
            .ok_or_else(|| Error::provider(format!("assistant provider missing: {provider_id}")))?;
        let mut req = ChatRequest::new(self.fallback_model(), messages);
        req.api_key_id = self.cfg.api_key_id.clone();
        req.stream = true;
        req.temperature = Some(0.5);
        let mut inner = provider.chat(req).await?;

        let store = self.store.clone();
        let friend_id = self.friend.id.clone();
        let prompt_for_post = prompt.clone();
        let assistant = self.clone_for_post();
        let turn_id = ctx
            .history
            .last()
            .map(|m| m.turn_id.clone())
            .unwrap_or_else(|| "unknown".into());

        let s = stream! {
            let mut full = String::new();
            let mut model_used: Option<String> = None;
            let mut tokens_in: i64 = 0;
            let mut tokens_out: i64 = 0;
            while let Some(item) = inner.next().await {
                match item {
                    Ok(ProviderEvent::Token(t)) => {
                        full.push_str(&t);
                        yield AgentEvent::Token(t);
                    }
                    Ok(ProviderEvent::Thinking(t)) => yield AgentEvent::Thinking(t),
                    Ok(ProviderEvent::Done { usage, model, .. }) => {
                        model_used = Some(model);
                        tokens_in = usage.prompt_tokens;
                        tokens_out = usage.completion_tokens;
                    }
                    Err(e) => {
                        yield AgentEvent::Error(e.to_string());
                        return;
                    }
                }
            }
            yield AgentEvent::Done(ProviderUsageInfo {
                model: model_used,
                tokens_in,
                tokens_out,
            });

            tokio::spawn(async move {
                let global = store.get_assistant_global_settings().await.unwrap_or_default();
                let is_builtin = store
                    .builtin_assistant_id()
                    .await
                    .ok()
                    .flatten()
                    .is_some_and(|id| id == friend_id);
                if is_builtin && global.observe_enabled {
                    let summary = format!(
                        "[协助记录]\n用户：{}\n助理：{}",
                        crate::assistant_accumulation::truncate_chars(&prompt_for_post, 280),
                        crate::assistant_accumulation::truncate_chars(&full, 400),
                    );
                    let _ = store
                        .insert_memory(crate::store::memory::NewMemory {
                            owner_friend_id: friend_id.clone(),
                            kind: crate::assistant_accumulation::MEMORY_KIND_MEMO.to_string(),
                            content: summary,
                            source_message_id: None,
                            weight: 0.5,
                            pinned: false,
                        })
                        .await;
                }
                if global.auto_extract_memories {
                    if let Err(e) = assistant.extract_memories(&prompt_for_post, &full).await {
                        tracing::warn!(err=%e, "assistant.extract_memories failed");
                    }
                }
                if global.evolution_enabled {
                    if let Err(e) = assistant.reflect(&turn_id, &prompt_for_post, &full).await {
                        tracing::warn!(err=%e, "assistant.reflect failed");
                    }
                }
                if global.auto_consolidate {
                    if let Err(e) = store.consolidate_memories(&friend_id).await {
                        tracing::warn!(err=%e, "consolidate_memories failed");
                    }
                }
            });
        };
        Ok(Box::pin(s))
    }

    async fn judge(&self, _ctx: ChatContext, _msg: &Message) -> Result<Judgment> {
        Ok(Judgment {
            should_reply: true,
            confidence: 0.7,
            reason: Some("Hex 助理愿意担当主持".into()),
            suggested_delay_ms: 200,
            source: None,
        })
    }
}

impl AssistantAgent {
    fn clone_for_post(&self) -> Self {
        Self {
            friend: self.friend.clone(),
            store: self.store.clone(),
            providers: self.providers.clone(),
            cfg: self.cfg.clone(),
            skills: self.skills.clone(),
        }
    }
}

fn json_array_from(s: &str) -> Option<String> {
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

fn json_object_from(s: &str) -> Option<String> {
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

#[allow(dead_code)]
pub fn placate(_: BackendKind) {}
