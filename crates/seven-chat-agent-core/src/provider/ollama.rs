use std::sync::Arc;
use std::time::Duration;

use async_stream::try_stream;
use async_trait::async_trait;
use bytes::Bytes;
use futures::stream::{BoxStream, StreamExt};
use reqwest::Client;
use serde_json::{json, Value};

use crate::domain::Provider;
use crate::provider::openai_compat::KeyResolver;
use crate::provider::types::{ChatRequest, ProviderEvent, ProviderUsage};
use crate::provider::ModelProvider;
use crate::{Error, Result};

pub struct OllamaProvider {
    descriptor: Provider,
    client: Client,
    _keys: Arc<dyn KeyResolver>,
}

impl OllamaProvider {
    pub fn new(descriptor: Provider, keys: Arc<dyn KeyResolver>) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(600))
            .build()
            .expect("reqwest client");
        Self {
            descriptor,
            client,
            _keys: keys,
        }
    }
}

#[async_trait]
impl ModelProvider for OllamaProvider {
    fn descriptor(&self) -> &Provider {
        &self.descriptor
    }

    async fn chat(
        &self,
        req: ChatRequest,
    ) -> Result<BoxStream<'static, Result<ProviderEvent>>> {
        let base = self
            .descriptor
            .base_url
            .trim_end_matches('/')
            .trim_end_matches("/v1")
            .to_string();
        let url = format!("{base}/api/chat");

        let mut options = json!({});
        if let Some(t) = req.temperature {
            options["temperature"] = json!(t);
        }
        if let Some(p) = req.top_p {
            options["top_p"] = json!(p);
        }
        if let Some(m) = req.max_tokens {
            options["num_predict"] = json!(m);
        }
        let body = json!({
            "model": req.model,
            "messages": req.messages,
            "stream": req.stream,
            "options": options,
        });

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
            return Err(Error::provider(format!("ollama http {status}: {text}")));
        }

        let model_name = req.model.clone();

        if !req.stream {
            let v: Value = resp.json().await.map_err(Error::Http)?;
            let text = v
                .pointer("/message/content")
                .and_then(|s| s.as_str())
                .unwrap_or("")
                .to_string();
            let usage = ProviderUsage {
                prompt_tokens: v.get("prompt_eval_count").and_then(|v| v.as_i64()).unwrap_or(0),
                completion_tokens: v.get("eval_count").and_then(|v| v.as_i64()).unwrap_or(0),
            };
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
            while let Some(chunk) = byte_stream.next().await {
                let chunk: Bytes = chunk.map_err(Error::Http)?;
                buf.extend_from_slice(&chunk);
                while let Some(idx) = buf.iter().position(|&b| b == b'\n') {
                    let line = buf.drain(..idx + 1).collect::<Vec<u8>>();
                    let text = String::from_utf8_lossy(&line);
                    let trimmed = text.trim();
                    if trimmed.is_empty() {
                        continue;
                    }
                    let v: Value = match serde_json::from_str(trimmed) {
                        Ok(v) => v,
                        Err(_) => continue,
                    };
                    if let Some(text) = v.pointer("/message/content").and_then(|s| s.as_str()) {
                        if !text.is_empty() {
                            yield ProviderEvent::Token(text.to_string());
                        }
                    }
                    if let Some(n) = v.get("prompt_eval_count").and_then(|v| v.as_i64()) {
                        usage_acc.prompt_tokens = n;
                    }
                    if let Some(n) = v.get("eval_count").and_then(|v| v.as_i64()) {
                        usage_acc.completion_tokens = n;
                    }
                    if v.get("done").and_then(|v| v.as_bool()).unwrap_or(false) {
                        let model = v.get("model").and_then(|s| s.as_str()).unwrap_or(&model_name).to_string();
                        yield ProviderEvent::Done { usage: usage_acc.clone(), finish_reason: None, model };
                        return;
                    }
                }
            }
            yield ProviderEvent::Done { usage: usage_acc, finish_reason: None, model: model_name };
        };
        Ok(Box::pin(s))
    }
}
