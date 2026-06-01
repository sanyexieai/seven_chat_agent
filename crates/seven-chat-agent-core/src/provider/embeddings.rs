use std::time::Duration;

use reqwest::Client;
use serde::Deserialize;

use crate::domain::Provider;
use crate::provider::registry::ProviderRegistry;
use crate::{Error, Result};

/// OpenAI 兼容 `POST /embeddings`。
pub async fn create_openai_embedding(
    registry: &ProviderRegistry,
    provider: &Provider,
    model: &str,
    text: &str,
    api_key_id: Option<&str>,
) -> Result<Vec<f32>> {
    let base = provider.base_url.trim_end_matches('/').to_string();
    let url = format!("{base}/embeddings");
    let secret = registry
        .resolve_provider_secret(&provider.id, api_key_id)
        .await?
        .ok_or_else(|| Error::provider(format!("no API key for embedding provider {}", provider.id)))?;

    let client = Client::builder()
        .timeout(Duration::from_secs(60))
        .build()
        .map_err(|e| Error::provider(e.to_string()))?;

    let body = serde_json::json!({
        "model": model,
        "input": text,
    });

    let resp = client
        .post(&url)
        .header("content-type", "application/json")
        .header("authorization", format!("Bearer {secret}"))
        .json(&body)
        .send()
        .await
        .map_err(Error::Http)?;

    if !resp.status().is_success() {
        let status = resp.status();
        let text = resp.text().await.unwrap_or_default();
        return Err(Error::provider(format!(
            "embeddings http {status}: {text}"
        )));
    }

    let parsed: EmbeddingResponse = resp.json().await.map_err(Error::Http)?;
    let emb = parsed
        .data
        .into_iter()
        .next()
        .and_then(|d| d.embedding)
        .ok_or_else(|| Error::provider("embeddings response empty"))?;
    Ok(emb)
}

#[derive(Debug, Deserialize)]
struct EmbeddingResponse {
    data: Vec<EmbeddingData>,
}

#[derive(Debug, Deserialize)]
struct EmbeddingData {
    embedding: Option<Vec<f32>>,
}

impl ProviderRegistry {
    pub async fn embed_text(
        &self,
        provider_id: &str,
        model: &str,
        text: &str,
        api_key_id: Option<&str>,
    ) -> Result<Vec<f32>> {
        let handle = self
            .get(provider_id)
            .ok_or_else(|| Error::provider(format!("provider missing: {provider_id}")))?;
        let provider = handle.descriptor().clone();
        let input = text.trim();
        if input.is_empty() {
            return Err(Error::bad_request("embed_text: empty input"));
        }
        create_openai_embedding(self, &provider, model, input, api_key_id).await
    }
}
