mod cli;
mod provider;
mod worker_bee;

use crate::domain::Friend;
use crate::provider::types::{ChatMessage, ProviderUsage};
use crate::provider::ProviderRegistry;
use crate::Result;

pub use cli::CliInferenceBackend;
pub use provider::ProviderInferenceBackend;
pub use worker_bee::WorkerBeeInferenceBackend;

use super::config::{InferenceBackend, RuntimeProfile};

#[derive(Debug, Clone, Default)]
pub struct ThinkResult {
    pub text: String,
    pub label: String,
    pub usage: ProviderUsage,
}

#[derive(Debug, Clone)]
pub enum ThinkBackend {
    Provider(ProviderInferenceBackend),
    Cli(CliInferenceBackend),
    WorkerBee(WorkerBeeInferenceBackend),
}

impl ThinkBackend {
    pub fn from_profile(friend: &Friend, profile: &RuntimeProfile) -> Self {
        match &profile.inference {
            InferenceBackend::WorkerBee(w) => ThinkBackend::WorkerBee(WorkerBeeInferenceBackend {
                provider: w.provider.clone(),
            }),
            InferenceBackend::ExternalCli(c) => ThinkBackend::Cli(CliInferenceBackend {
                preset: c.preset.clone(),
                cmd: c.cmd.clone(),
                cwd: profile.workspace_cwd.clone(),
                friend_id: friend.id.clone(),
            }),
        }
    }

    pub async fn think(
        &self,
        providers: &ProviderRegistry,
        profile: &RuntimeProfile,
        messages: &[ChatMessage],
    ) -> Result<ThinkResult> {
        match self {
            ThinkBackend::Provider(p) => p.complete(providers, profile, messages).await,
            ThinkBackend::Cli(c) => c.complete(messages).await,
            ThinkBackend::WorkerBee(w) => w.complete(providers, profile, messages).await,
        }
    }
}
