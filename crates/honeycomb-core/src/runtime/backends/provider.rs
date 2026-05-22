use crate::domain::ApiModelRef;
use crate::provider::types::{ChatMessage, ChatRequest, ProviderEvent, ProviderUsage};
use crate::provider::ProviderRegistry;
use crate::{Error, Result};

use super::{ThinkResult};
use crate::runtime::config::RuntimeProfile;

/// **API** 推理后端：通过 Provider 矩阵兼任 OpenAI / Anthropic / Gemini / DeepSeek / Ollama / 兼容端点等各家平台。
#[derive(Debug, Clone)]
pub struct ProviderInferenceBackend {
    pub provider_id: String,
    pub model: String,
    pub api_key_id: Option<String>,
    pub model_chain: Vec<ApiModelRef>,
}

impl ProviderInferenceBackend {
    pub async fn complete(
        &self,
        providers: &ProviderRegistry,
        profile: &RuntimeProfile,
        messages: &[ChatMessage],
    ) -> Result<ThinkResult> {
        let chain = if self.model_chain.is_empty() {
            vec![ApiModelRef {
                provider_id: self.provider_id.clone(),
                model: self.model.clone(),
                api_key_id: self.api_key_id.clone(),
            }]
        } else {
            self.model_chain.clone()
        };

        let mut last_err = None;
        for target in chain {
            let provider = match providers.get(&target.provider_id) {
                Some(p) => p,
                None => continue,
            };
            let mut req = ChatRequest::new(target.model.clone(), messages.to_vec());
            req.api_key_id = target.api_key_id.clone();
            req.stream = false;
            req.temperature = Some(profile.temperature);
            req.max_tokens = Some(profile.max_tokens);
            match provider.chat(req).await {
                Ok(mut stream) => {
                    use futures::StreamExt;
                    let mut buf = String::new();
                    let mut usage = ProviderUsage::default();
                    let mut model = target.model.clone();
                    while let Some(item) = stream.next().await {
                        match item? {
                            ProviderEvent::Token(t) => buf.push_str(&t),
                            ProviderEvent::Done {
                                usage: u,
                                model: m,
                                ..
                            } => {
                                usage = u;
                                model = m;
                            }
                            ProviderEvent::Thinking(_) => {}
                        }
                    }
                    let label = format!("{}/{}", target.provider_id, model);
                    return Ok(ThinkResult {
                        text: buf,
                        label,
                        usage,
                    });
                }
                Err(e) => last_err = Some(e),
            }
        }
        Err(last_err.unwrap_or_else(|| {
            Error::provider("honeycomb: 推理后端 Provider 全部失败（请在设置里配置 API Key）")
        }))
    }
}
