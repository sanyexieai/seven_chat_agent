use async_stream::stream;
use async_trait::async_trait;
use futures::stream::{BoxStream, StreamExt};
use serde::Deserialize;
use tracing::warn;

use crate::agent::{Agent, AgentEvent, AgentKind, ChatContext, Judgment, ProviderUsageInfo};
use crate::domain::{ApiBackendConfig, ApiModelRef, Friend, Message, SenderKind};
use crate::provider::types::{ChatMessage, ChatRequest, ProviderEvent};
use crate::provider::ProviderRegistry;
use crate::{Error, Result};

use std::sync::Arc;

pub struct ApiAgent {
    friend: Friend,
    providers: Arc<ProviderRegistry>,
}

impl ApiAgent {
    pub fn new(friend: Friend, providers: Arc<ProviderRegistry>) -> Result<Self> {
        Ok(Self { friend, providers })
    }

    fn config(&self) -> Result<ApiBackendConfig> {
        serde_json::from_value(self.friend.backend_config.clone())
            .map_err(|e| Error::Config(format!("invalid api backend_config: {e}")))
    }

    fn build_system_prompt(&self, ctx: &ChatContext) -> String {
        let mut s = self.friend.system_prompt.clone();
        if let Some(p) = ctx.group_settings.as_ref().and_then(|g| g.extra_system_prompt.clone()) {
            if !p.trim().is_empty() {
                s.push_str("\n\n");
                s.push_str(&p);
            }
        }
        if !self.friend.focus_tags.is_empty() {
            s.push_str("\n\n关注点：");
            s.push_str(&self.friend.focus_tags.join("、"));
        }
        if let Some(per) = &self.friend.personality {
            s.push_str("\n性格：");
            s.push_str(per);
        }
        s.push_str(&format!(
            "\n\n你的名字是「{}」。请用第一人称、自然的中文聊天风格回答。",
            self.friend.name
        ));
        s
    }

    fn build_messages(&self, ctx: &ChatContext, prompt: &str) -> Vec<ChatMessage> {
        let mut messages = vec![ChatMessage::system(self.build_system_prompt(ctx))];
        for m in &ctx.history {
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
            messages.push(ChatMessage {
                role: role.into(),
                content,
                name: None,
            });
        }
        messages.push(ChatMessage::user(prompt.to_string()));
        messages
    }
}

#[async_trait]
impl Agent for ApiAgent {
    fn kind(&self) -> AgentKind {
        AgentKind::Api
    }

    async fn send(
        &self,
        ctx: ChatContext,
        prompt: String,
    ) -> Result<BoxStream<'static, AgentEvent>> {
        let cfg = self.config()?;
        let chain = build_chain(&cfg);
        let providers = self.providers.clone();
        let messages = self.build_messages(&ctx, &prompt);
        let params = cfg.params.clone();

        for (idx, target) in chain.iter().enumerate() {
            let provider = match providers.get(&target.provider_id) {
                Some(p) => p,
                None => {
                    warn!(idx, provider = %target.provider_id, "provider missing, falling back");
                    continue;
                }
            };
            let mut req = ChatRequest::new(target.model.clone(), messages.clone());
            req.api_key_id = target.api_key_id.clone();
            req.temperature = params.temperature;
            req.top_p = params.top_p;
            req.max_tokens = params.max_tokens;
            req.stream = true;
            match provider.chat(req).await {
                Ok(stream_inner) => {
                    let s = stream! {
                        let mut inner = stream_inner;
                        let mut model_used: Option<String> = None;
                        let mut tokens_in: i64 = 0;
                        let mut tokens_out: i64 = 0;
                        while let Some(item) = inner.next().await {
                            match item {
                                Ok(ProviderEvent::Token(t)) => yield AgentEvent::Token(t),
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
                        yield AgentEvent::Done(ProviderUsageInfo { model: model_used, tokens_in, tokens_out });
                    };
                    return Ok(Box::pin(s));
                }
                Err(e) => {
                    warn!(idx, provider = %target.provider_id, model = %target.model, err = %e, "chain step failed");
                }
            }
        }
        Err(Error::provider("all providers in chain failed"))
    }

    async fn judge(&self, ctx: ChatContext, msg: &Message) -> Result<Judgment> {
        let cfg = self.config()?;
        let judge_provider_id = self
            .friend
            .judge_provider_ref
            .clone()
            .or_else(|| Some(cfg.provider_id.clone()))
            .ok_or_else(|| Error::Config("no judge provider".into()))?;
        let provider = self
            .providers
            .get(&judge_provider_id)
            .ok_or_else(|| Error::provider("judge provider not found"))?;

        let history_excerpt = ctx
            .history
            .iter()
            .rev()
            .take(6)
            .rev()
            .map(|m| format!("[{}]: {}", m.sender_name, truncate(&m.content, 120)))
            .collect::<Vec<_>>()
            .join("\n");
        let prompt = format!(
            "你正在扮演群聊里的「{}」（{}），关注点：{}。\n下面是最近的对话片段：\n{}\n\n新消息来自 [{}]：\n{}\n\n判断：你是否应该出声回应这条消息？只输出严格的 JSON：{{\"should_reply\": true/false, \"confidence\": 0.0-1.0, \"reason\": \"...\", \"suggested_delay_ms\": 0}}",
            self.friend.name,
            self.friend.personality.clone().unwrap_or_default(),
            self.friend.focus_tags.join("、"),
            history_excerpt,
            msg.sender_name,
            truncate(&msg.content, 600),
        );

        let req = ChatRequest {
            model: cfg.model.clone(),
            api_key_id: cfg.api_key_id.clone(),
            messages: vec![
                ChatMessage::system("你是一个判断助手，只输出 JSON。"),
                ChatMessage::user(prompt),
            ],
            temperature: Some(0.3),
            top_p: None,
            max_tokens: Some(200),
            stream: false,
            response_format_json: true,
        };
        let mut stream = provider.chat(req).await?;
        let mut buf = String::new();
        while let Some(item) = stream.next().await {
            match item? {
                ProviderEvent::Token(t) => buf.push_str(&t),
                ProviderEvent::Done { .. } | ProviderEvent::Thinking(_) => {}
            }
        }
        let parsed: Judgment = match serde_json::from_str::<JudgmentRaw>(&buf) {
            Ok(r) => r.into_judgment(),
            Err(_) => {
                let body = extract_json(&buf).unwrap_or_default();
                serde_json::from_str::<JudgmentRaw>(&body)
                    .map(|r| r.into_judgment())
                    .unwrap_or(Judgment {
                        should_reply: false,
                        confidence: 0.0,
                        reason: Some("judge parse failed".into()),
                        suggested_delay_ms: 0,
                        source: None,
                    })
            }
        };
        Ok(parsed)
    }
}

#[derive(Debug, Deserialize)]
struct JudgmentRaw {
    #[serde(default)]
    should_reply: bool,
    #[serde(default)]
    confidence: f32,
    #[serde(default)]
    reason: Option<String>,
    #[serde(default)]
    suggested_delay_ms: u64,
}

impl JudgmentRaw {
    fn into_judgment(self) -> Judgment {
        Judgment {
            should_reply: self.should_reply,
            confidence: self.confidence.clamp(0.0, 1.0),
            reason: self.reason,
            suggested_delay_ms: self.suggested_delay_ms,
            source: None,
        }
    }
}

fn truncate(s: &str, n: usize) -> String {
    if s.chars().count() <= n {
        s.to_string()
    } else {
        let mut out: String = s.chars().take(n).collect();
        out.push('…');
        out
    }
}

fn build_chain(cfg: &ApiBackendConfig) -> Vec<ApiModelRef> {
    let mut chain = Vec::with_capacity(1 + cfg.model_chain.len());
    chain.push(ApiModelRef {
        provider_id: cfg.provider_id.clone(),
        model: cfg.model.clone(),
        api_key_id: cfg.api_key_id.clone(),
    });
    chain.extend(cfg.model_chain.iter().cloned());
    chain
}

fn extract_json(s: &str) -> Option<String> {
    let start = s.find('{')?;
    let mut depth = 0i32;
    let mut end = None;
    for (i, c) in s[start..].char_indices() {
        match c {
            '{' => depth += 1,
            '}' => {
                depth -= 1;
                if depth == 0 {
                    end = Some(start + i + 1);
                    break;
                }
            }
            _ => {}
        }
    }
    end.map(|e| s[start..e].to_string())
}
