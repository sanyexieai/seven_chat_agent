use std::sync::Arc;
use std::time::Duration;

use async_stream::try_stream;
use async_trait::async_trait;
use bytes::Bytes;
use futures::stream::{BoxStream, StreamExt};
use reqwest::Client;
use serde_json::{json, Value};

use crate::domain::Provider;
use crate::provider::openai_compat::{KeyMaterial, KeyResolver};
use crate::provider::chat_content::chat_content_to_text;
use crate::provider::types::{ChatMessage, ChatRequest, ProviderEvent, ProviderUsage};
use crate::provider::ModelProvider;
use crate::store::SecretVault;
use crate::{Error, Result};

pub struct GeminiProvider {
    descriptor: Provider,
    client: Client,
    vault: SecretVault,
    keys: Arc<dyn KeyResolver>,
}

impl GeminiProvider {
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
impl ModelProvider for GeminiProvider {
    fn descriptor(&self) -> &Provider {
        &self.descriptor
    }

    async fn chat(
        &self,
        req: ChatRequest,
    ) -> Result<BoxStream<'static, Result<ProviderEvent>>> {
        let base = self.descriptor.base_url.trim_end_matches('/').to_string();
        let stream_path = if req.stream {
            "streamGenerateContent"
        } else {
            "generateContent"
        };

        let key = self
            .keys
            .resolve(&self.descriptor.id, req.api_key_id.as_deref())
            .await?
            .or_else(|| {
                self.vault
                    .get("env:GEMINI_API_KEY")
                    .map(|s| KeyMaterial {
                        key_id: "env".into(),
                        secret: s,
                    })
            })
            .ok_or_else(|| Error::provider("gemini api key missing"))?;

        let model = req.model.clone();
        let model_path = if model.contains('/') {
            model.clone()
        } else {
            format!("models/{model}")
        };
        let url = format!(
            "{base}/{model_path}:{stream_path}?alt=sse&key={api_key}",
            api_key = key.secret,
        );

        let (system, contents) = build_contents(req.messages);
        let mut gen_config = json!({});
        if let Some(t) = req.temperature {
            gen_config["temperature"] = json!(t);
        }
        if let Some(p) = req.top_p {
            gen_config["topP"] = json!(p);
        }
        if let Some(m) = req.max_tokens {
            gen_config["maxOutputTokens"] = json!(m);
        }
        if req.response_format_json {
            gen_config["responseMimeType"] = json!("application/json");
        }
        let mut body = json!({
            "contents": contents,
            "generationConfig": gen_config,
        });
        if let Some(s) = system {
            body["systemInstruction"] = json!({
                "parts": [ { "text": s } ]
            });
        }

        let resp = self
            .client
            .post(&url)
            .header("content-type", "application/json")
            .json(&body)
            .send()
            .await
            .map_err(Error::Http)?;
        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            return Err(Error::provider(format!("gemini http {status}: {text}")));
        }

        let resolver = self.keys.clone();
        let key_for_usage = key.clone();
        let model_name = req.model.clone();

        if !req.stream {
            let v: Value = resp.json().await.map_err(Error::Http)?;
            let (text, usage) = extract_gemini_payload(&v);
            let _ = resolver.record_usage(&key_for_usage.key_id, &usage).await;
            let s = try_stream! {
                yield ProviderEvent::Token(text);
                yield ProviderEvent::Done { usage, finish_reason: None, model: model_name };
            };
            return Ok(Box::pin(s));
        }

        let mut byte_stream = resp.bytes_stream();
        let s = try_stream! {
            let mut buf = Vec::<u8>::new();
            let mut usage_acc = ProviderUsage::default();
            let mut model_emitted = model_name.clone();
            while let Some(chunk) = byte_stream.next().await {
                let chunk: Bytes = chunk.map_err(Error::Http)?;
                buf.extend_from_slice(&chunk);
                while let Some(idx) = find_double_newline(&buf) {
                    let raw = buf.drain(..idx + 2).collect::<Vec<u8>>();
                    let event_str = String::from_utf8_lossy(&raw);
                    let payload = event_str
                        .lines()
                        .filter_map(|l| l.strip_prefix("data: "))
                        .collect::<Vec<_>>()
                        .join("\n");
                    if payload.trim().is_empty() {
                        continue;
                    }
                    let v: Value = match serde_json::from_str(&payload) {
                        Ok(v) => v,
                        Err(_) => continue,
                    };
                    if let Some(model) = v.get("modelVersion").and_then(|v| v.as_str()) {
                        model_emitted = model.to_string();
                    }
                    if let Some(candidates) = v.get("candidates").and_then(|c| c.as_array()) {
                        for c in candidates {
                            if let Some(parts) = c.pointer("/content/parts").and_then(|p| p.as_array()) {
                                for p in parts {
                                    if let Some(text) = p.get("text").and_then(|s| s.as_str()) {
                                        yield ProviderEvent::Token(text.to_string());
                                    }
                                }
                            }
                        }
                    }
                    if let Some(meta) = v.get("usageMetadata") {
                        if let Some(n) = meta.get("promptTokenCount").and_then(|v| v.as_i64()) {
                            usage_acc.prompt_tokens = n;
                        }
                        if let Some(n) = meta.get("candidatesTokenCount").and_then(|v| v.as_i64()) {
                            usage_acc.completion_tokens = n;
                        }
                    }
                }
            }
            resolver.record_usage(&key_for_usage.key_id, &usage_acc).await.ok();
            yield ProviderEvent::Done { usage: usage_acc, finish_reason: None, model: model_emitted };
        };
        Ok(Box::pin(s))
    }
}

fn find_double_newline(buf: &[u8]) -> Option<usize> {
    buf.windows(2).position(|w| w == b"\n\n")
}

fn build_contents(msgs: Vec<ChatMessage>) -> (Option<String>, Vec<Value>) {
    let mut system_parts = Vec::new();
    let mut contents = Vec::new();
    for m in msgs {
        if m.role == "system" {
            system_parts.push(chat_content_to_text(&m.content));
            continue;
        }
        let role = if m.role == "assistant" { "model" } else { "user" };
        contents.push(json!({
            "role": role,
            "parts": [ { "text": chat_content_to_text(&m.content) } ]
        }));
    }
    let system = if system_parts.is_empty() {
        None
    } else {
        Some(system_parts.join("\n\n"))
    };
    (system, contents)
}

fn extract_gemini_payload(v: &Value) -> (String, ProviderUsage) {
    let mut text = String::new();
    if let Some(candidates) = v.get("candidates").and_then(|c| c.as_array()) {
        for c in candidates {
            if let Some(parts) = c.pointer("/content/parts").and_then(|p| p.as_array()) {
                for p in parts {
                    if let Some(t) = p.get("text").and_then(|s| s.as_str()) {
                        text.push_str(t);
                    }
                }
            }
        }
    }
    let usage = if let Some(meta) = v.get("usageMetadata") {
        ProviderUsage {
            prompt_tokens: meta
                .get("promptTokenCount")
                .and_then(|v| v.as_i64())
                .unwrap_or(0),
            completion_tokens: meta
                .get("candidatesTokenCount")
                .and_then(|v| v.as_i64())
                .unwrap_or(0),
        }
    } else {
        ProviderUsage::default()
    };
    (text, usage)
}
