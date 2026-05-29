use std::sync::Arc;
use std::time::Duration;

use async_stream::try_stream;
use async_trait::async_trait;
use eventsource_stream::Eventsource;
use futures::stream::{BoxStream, StreamExt};
use reqwest::Client;
use serde::Deserialize;

use crate::domain::Provider;
use crate::provider::openai_compat::KeyResolver;
use crate::provider::types::{ChatMessage, ChatRequest, ProviderEvent, ProviderUsage};
use crate::provider::ModelProvider;
use crate::store::SecretVault;
use crate::{Error, Result};

pub struct AnthropicProvider {
    descriptor: Provider,
    client: Client,
    vault: SecretVault,
    keys: Arc<dyn KeyResolver>,
}

impl AnthropicProvider {
    pub fn new(
        descriptor: Provider,
        vault: SecretVault,
        keys: Arc<dyn KeyResolver>,
    ) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(180))
            .build()
            .expect("reqwest client");
        Self {
            descriptor,
            client,
            vault,
            keys,
        }
    }
}

#[async_trait]
impl ModelProvider for AnthropicProvider {
    fn descriptor(&self) -> &Provider {
        &self.descriptor
    }

    async fn chat(
        &self,
        req: ChatRequest,
    ) -> Result<BoxStream<'static, Result<ProviderEvent>>> {
        let base = self.descriptor.base_url.trim_end_matches('/').to_string();
        let url = format!("{base}/v1/messages");

        let key = self
            .keys
            .resolve(&self.descriptor.id, req.api_key_id.as_deref())
            .await?
            .or_else(|| {
                self.vault
                    .get("env:ANTHROPIC_API_KEY")
                    .map(|s| crate::provider::openai_compat::KeyMaterial {
                        key_id: "env".into(),
                        secret: s,
                    })
            })
            .ok_or_else(|| Error::provider("anthropic api key missing"))?;

        let (system, user_messages) = split_system(req.messages);
        let mut body = serde_json::json!({
            "model": req.model,
            "messages": user_messages,
            "max_tokens": req.max_tokens.unwrap_or(2048),
            "stream": req.stream,
        });
        if let Some(s) = system {
            body["system"] = serde_json::Value::String(s);
        }
        if let Some(t) = req.temperature {
            body["temperature"] = serde_json::json!(t);
        }
        if let Some(p) = req.top_p {
            body["top_p"] = serde_json::json!(p);
        }

        let resp = self
            .client
            .post(&url)
            .header("content-type", "application/json")
            .header("anthropic-version", "2023-06-01")
            .header("x-api-key", &key.secret)
            .json(&body)
            .send()
            .await
            .map_err(Error::Http)?;
        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            return Err(Error::provider(format!("anthropic http {status}: {text}")));
        }

        let resolver = self.keys.clone();
        let key_for_usage = key.clone();
        let model_name = req.model.clone();

        if !req.stream {
            let v: AnthropicResponse = resp.json().await.map_err(Error::Http)?;
            let text = v
                .content
                .iter()
                .filter_map(|c| {
                    if c.type_field == "text" {
                        c.text.clone()
                    } else {
                        None
                    }
                })
                .collect::<Vec<_>>()
                .join("");
            let usage = ProviderUsage {
                prompt_tokens: v.usage.input_tokens.unwrap_or(0),
                completion_tokens: v.usage.output_tokens.unwrap_or(0),
            };
            let _ = resolver.record_usage(&key_for_usage.key_id, &usage).await;
            let s = try_stream! {
                yield ProviderEvent::Token(text);
                yield ProviderEvent::Done { usage, finish_reason: None, model: model_name };
            };
            return Ok(Box::pin(s));
        }

        let byte_stream = resp.bytes_stream();
        let mut event_stream = byte_stream.eventsource();

        let s = try_stream! {
            let mut usage_acc = ProviderUsage::default();
            let mut finish_reason: Option<String> = None;
            let mut model_emitted = model_name.clone();
            while let Some(ev) = event_stream.next().await {
                let ev = ev.map_err(|e| Error::provider(format!("sse error: {e}")))?;
                if ev.data.trim().is_empty() {
                    continue;
                }
                let v: serde_json::Value = match serde_json::from_str(&ev.data) {
                    Ok(v) => v,
                    Err(_) => continue,
                };
                let t = v.get("type").and_then(|t| t.as_str()).unwrap_or("");
                match t {
                    "message_start" => {
                        if let Some(model) = v.pointer("/message/model").and_then(|s| s.as_str()) {
                            model_emitted = model.to_string();
                        }
                        if let Some(u) = v.pointer("/message/usage") {
                            if let Some(n) = u.get("input_tokens").and_then(|v| v.as_i64()) {
                                usage_acc.prompt_tokens = n;
                            }
                        }
                    }
                    "content_block_delta" => {
                        if let Some(delta) = v.get("delta") {
                            let dt = delta.get("type").and_then(|s| s.as_str()).unwrap_or("");
                            match dt {
                                "text_delta" => {
                                    if let Some(text) = delta.get("text").and_then(|s| s.as_str()) {
                                        yield ProviderEvent::Token(text.to_string());
                                    }
                                }
                                "thinking_delta" => {
                                    if let Some(text) = delta.get("thinking").and_then(|s| s.as_str()) {
                                        yield ProviderEvent::Thinking(text.to_string());
                                    }
                                }
                                _ => {}
                            }
                        }
                    }
                    "message_delta" => {
                        if let Some(u) = v.get("usage") {
                            if let Some(n) = u.get("output_tokens").and_then(|v| v.as_i64()) {
                                usage_acc.completion_tokens = n;
                            }
                        }
                        if let Some(reason) = v.pointer("/delta/stop_reason").and_then(|s| s.as_str()) {
                            finish_reason = Some(reason.to_string());
                        }
                    }
                    "message_stop" => break,
                    _ => {}
                }
            }
            resolver.record_usage(&key_for_usage.key_id, &usage_acc).await.ok();
            yield ProviderEvent::Done { usage: usage_acc, finish_reason, model: model_emitted };
        };
        Ok(Box::pin(s))
    }
}

fn split_system(msgs: Vec<ChatMessage>) -> (Option<String>, Vec<ChatMessage>) {
    let mut system_parts: Vec<String> = Vec::new();
    let mut rest = Vec::new();
    for m in msgs {
        if m.role == "system" {
            system_parts.push(m.content);
        } else {
            rest.push(m);
        }
    }
    let system = if system_parts.is_empty() {
        None
    } else {
        Some(system_parts.join("\n\n"))
    };
    (system, rest)
}

#[derive(Debug, Deserialize)]
struct AnthropicResponse {
    content: Vec<AnthropicContentBlock>,
    usage: AnthropicUsage,
}

#[derive(Debug, Deserialize)]
struct AnthropicContentBlock {
    #[serde(rename = "type")]
    type_field: String,
    text: Option<String>,
}

#[derive(Debug, Deserialize, Default)]
struct AnthropicUsage {
    input_tokens: Option<i64>,
    output_tokens: Option<i64>,
}
