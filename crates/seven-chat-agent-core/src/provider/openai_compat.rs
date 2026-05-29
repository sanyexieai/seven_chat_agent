use std::sync::Arc;
use std::time::Duration;

use async_stream::try_stream;
use async_trait::async_trait;
use eventsource_stream::Eventsource;
use futures::stream::{BoxStream, StreamExt};
use reqwest::Client;
use serde::{Deserialize, Serialize};

use crate::domain::Provider;
use crate::provider::types::{ChatMessage, ChatRequest, ProviderEvent, ProviderUsage};
use crate::provider::ModelProvider;
use crate::store::SecretVault;
use crate::{Error, Result};

pub struct OpenAiCompatProvider {
    descriptor: Provider,
    client: Client,
    vault: SecretVault,
    keys: Arc<dyn KeyResolver>,
}

#[async_trait]
pub trait KeyResolver: Send + Sync {
    async fn resolve(&self, provider_id: &str, hint: Option<&str>) -> Result<Option<KeyMaterial>>;
    async fn record_usage(&self, key_id: &str, usage: &ProviderUsage) -> Result<()>;
}

#[derive(Debug, Clone)]
pub struct KeyMaterial {
    pub key_id: String,
    pub secret: String,
}

impl OpenAiCompatProvider {
    pub fn new(
        descriptor: Provider,
        vault: SecretVault,
        keys: Arc<dyn KeyResolver>,
    ) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(120))
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
impl ModelProvider for OpenAiCompatProvider {
    fn descriptor(&self) -> &Provider {
        &self.descriptor
    }

    async fn chat(
        &self,
        req: ChatRequest,
    ) -> Result<BoxStream<'static, Result<ProviderEvent>>> {
        let base = self.descriptor.base_url.trim_end_matches('/').to_string();
        let url = format!("{base}/chat/completions");

        let key = self
            .keys
            .resolve(&self.descriptor.id, req.api_key_id.as_deref())
            .await?;

        let mut request_builder = self.client.post(&url).header("content-type", "application/json");
        if let Some(km) = &key {
            request_builder = request_builder
                .header("authorization", format!("Bearer {}", km.secret));
        } else if let Some(v) = self.vault.get(&format!("env:{}", env_var_name(&self.descriptor.id))) {
            request_builder = request_builder.header("authorization", format!("Bearer {v}"));
        }

        let mut body = serde_json::json!({
            "model": req.model,
            "messages": req.messages,
            "stream": req.stream,
        });
        if let Some(t) = req.temperature {
            body["temperature"] = serde_json::json!(t);
        }
        if let Some(p) = req.top_p {
            body["top_p"] = serde_json::json!(p);
        }
        if let Some(m) = req.max_tokens {
            body["max_tokens"] = serde_json::json!(m);
        }
        if req.response_format_json {
            body["response_format"] = serde_json::json!({"type": "json_object"});
        }
        if req.stream {
            body["stream_options"] = serde_json::json!({"include_usage": true});
        }

        let resp = request_builder
            .json(&body)
            .send()
            .await
            .map_err(Error::Http)?;
        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            return Err(Error::provider(format!(
                "openai_compat http {status}: {text}"
            )));
        }

        let key_for_usage = key.clone();
        let resolver = self.keys.clone();
        let model_name = req.model.clone();

        if !req.stream {
            let body: ChatCompletion = resp.json().await.map_err(Error::Http)?;
            let usage = body.usage.unwrap_or_default();
            if let Some(km) = &key_for_usage {
                resolver
                    .record_usage(&km.key_id, &ProviderUsage {
                        prompt_tokens: usage.prompt_tokens.unwrap_or(0),
                        completion_tokens: usage.completion_tokens.unwrap_or(0),
                    })
                    .await
                    .ok();
            }
            let text = body
                .choices
                .first()
                .and_then(|c| c.message.as_ref())
                .map(|m| m.content.clone())
                .unwrap_or_default();
            let usage = ProviderUsage {
                prompt_tokens: usage.prompt_tokens.unwrap_or(0),
                completion_tokens: usage.completion_tokens.unwrap_or(0),
            };
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
                let data = ev.data;
                if data.trim() == "[DONE]" {
                    break;
                }
                let chunk: ChatCompletionChunk = match serde_json::from_str(&data) {
                    Ok(c) => c,
                    Err(e) => {
                        Err(Error::provider(format!("decode sse chunk: {e} body={data}")))?;
                        return;
                    }
                };
                if let Some(m) = &chunk.model { model_emitted = m.clone(); }
                if let Some(usage) = chunk.usage {
                    if let Some(v) = usage.prompt_tokens { usage_acc.prompt_tokens = v; }
                    if let Some(v) = usage.completion_tokens { usage_acc.completion_tokens = v; }
                }
                if let Some(choice) = chunk.choices.into_iter().next() {
                    if let Some(reason) = choice.finish_reason {
                        finish_reason = Some(reason);
                    }
                    if let Some(delta) = choice.delta {
                        if let Some(t) = delta.reasoning_content {
                            if !t.is_empty() { yield ProviderEvent::Thinking(t); }
                        }
                        if let Some(t) = delta.content {
                            if !t.is_empty() { yield ProviderEvent::Token(t); }
                        }
                    }
                }
            }
            if let Some(km) = &key_for_usage {
                resolver.record_usage(&km.key_id, &usage_acc).await.ok();
            }
            yield ProviderEvent::Done { usage: usage_acc, finish_reason, model: model_emitted };
        };
        Ok(Box::pin(s))
    }
}

fn env_var_name(provider_id: &str) -> String {
    format!("{}_API_KEY", provider_id.to_uppercase().replace('-', "_"))
}

#[derive(Debug, Deserialize, Serialize, Default)]
struct UsageBlock {
    prompt_tokens: Option<i64>,
    completion_tokens: Option<i64>,
    total_tokens: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct ChatCompletion {
    choices: Vec<NonStreamChoice>,
    #[serde(default)]
    usage: Option<UsageBlock>,
}

#[derive(Debug, Deserialize)]
struct NonStreamChoice {
    message: Option<ChatMessage>,
}

#[derive(Debug, Deserialize)]
struct ChatCompletionChunk {
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    choices: Vec<StreamChoice>,
    #[serde(default)]
    usage: Option<UsageBlock>,
}

#[derive(Debug, Deserialize)]
struct StreamChoice {
    #[serde(default)]
    delta: Option<DeltaBlock>,
    #[serde(default)]
    finish_reason: Option<String>,
}

#[derive(Debug, Deserialize)]
struct DeltaBlock {
    #[serde(default)]
    content: Option<String>,
    #[serde(default)]
    reasoning_content: Option<String>,
}
