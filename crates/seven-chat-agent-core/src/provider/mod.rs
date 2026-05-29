pub mod anthropic;
pub mod gemini;
pub mod ollama;
pub mod openai_compat;
pub mod rate_limit;
pub mod registry;
pub mod types;

pub use registry::{ProviderHandle, ProviderRegistry};
pub use types::{ChatMessage, ChatRequest, ProviderEvent, ProviderUsage};

use async_trait::async_trait;
use futures::stream::BoxStream;

use crate::domain::{Provider, ProviderCapabilities};
use crate::Result;

#[async_trait]
pub trait ModelProvider: Send + Sync {
    fn descriptor(&self) -> &Provider;
    fn capabilities(&self) -> &ProviderCapabilities {
        &self.descriptor().capabilities
    }
    async fn chat(
        &self,
        req: ChatRequest,
    ) -> Result<BoxStream<'static, Result<ProviderEvent>>>;
}
