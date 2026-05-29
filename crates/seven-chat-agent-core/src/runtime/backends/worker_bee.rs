use crate::provider::types::ChatMessage;
use crate::provider::ProviderRegistry;
use crate::Result;

use super::provider::ProviderInferenceBackend;
use super::ThinkResult;
use crate::runtime::config::{ProviderInferenceConfig, RuntimeProfile};
use crate::runtime::resolve_worker_bee_provider;

/// 工蜂实例：推理走 **平台 Provider API**（DeepSeek/OpenAI 等）；`worker-bee` CLI 仅用于可选本地工具链。
#[derive(Debug, Clone)]
pub struct WorkerBeeInferenceBackend {
    pub provider: ProviderInferenceConfig,
}

impl WorkerBeeInferenceBackend {
    pub async fn complete(
        &self,
        providers: &ProviderRegistry,
        profile: &RuntimeProfile,
        messages: &[ChatMessage],
    ) -> Result<ThinkResult> {
        let resolved = resolve_worker_bee_provider(
            &self.provider.provider_id,
            &self.provider.model,
            self.provider.api_key_id.clone(),
        );
        let backend = ProviderInferenceBackend {
            provider_id: resolved.provider_id,
            model: resolved.model,
            api_key_id: resolved.api_key_id,
            model_chain: resolved.model_chain,
        };
        backend.complete(providers, profile, messages).await
    }
}
