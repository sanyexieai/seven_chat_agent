use std::sync::Arc;

use async_trait::async_trait;
use futures::StreamExt;

use seven_chat_agent_judge::{LlmJudgeInput, LlmJudgePort};

use crate::provider::types::{ChatMessage, ChatRequest, ProviderEvent};
use crate::provider::ProviderRegistry;

/// 使用 `ProviderRegistry` 执行 LLM judge。
pub struct ProviderLlmJudgePort {
    pub(crate) providers: Arc<ProviderRegistry>,
}

impl ProviderLlmJudgePort {
    pub fn new(providers: Arc<ProviderRegistry>) -> Self {
        Self { providers }
    }
}

#[async_trait]
impl LlmJudgePort for ProviderLlmJudgePort {
    async fn complete_json(&self, input: LlmJudgeInput) -> Result<String, String> {
        let provider = self
            .providers
            .get(&input.provider_id)
            .ok_or_else(|| format!("judge provider not found: {}", input.provider_id))?;
        let req = ChatRequest {
            model: input.model,
            api_key_id: input.api_key_id,
            messages: vec![
                ChatMessage::system(&input.system),
                ChatMessage::user(&input.user_prompt),
            ],
            temperature: Some(0.3),
            top_p: None,
            max_tokens: input.max_tokens.or(Some(200)),
            stream: false,
            response_format_json: true,
        };
        let mut stream = provider
            .chat(req)
            .await
            .map_err(|e| e.to_string())?;
        let mut buf = String::new();
        while let Some(item) = stream.next().await {
            match item.map_err(|e| e.to_string())? {
                ProviderEvent::Token(t) => buf.push_str(&t),
                ProviderEvent::Done { .. } | ProviderEvent::Thinking(_) => {}
            }
        }
        Ok(buf)
    }
}
