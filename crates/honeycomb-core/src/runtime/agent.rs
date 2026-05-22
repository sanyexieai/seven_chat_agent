use std::sync::Arc;

use async_trait::async_trait;
use futures::stream::BoxStream;

use crate::agent::api::ApiAgent;
use crate::agent::{Agent, AgentEvent, AgentKind, ChatContext, Judgment};
use crate::domain::{BackendKind, Friend, Message};
use crate::provider::ProviderRegistry;
use crate::store::SqliteStore;
use crate::Result;

use super::config::RuntimeProfile;
use super::engine::AgentRuntime;

/// 统一运行时 Agent：API / 助理 / CLI 好友共用记忆 + 工具循环。
pub struct UnifiedAgent {
    friend: Friend,
    profile: RuntimeProfile,
    runtime: Arc<AgentRuntime>,
    /// 群聊 judge 仍委托给 ApiAgent 逻辑（需 provider）。
    judge_delegate: Option<ApiAgent>,
}

impl UnifiedAgent {
    pub fn new(
        friend: Friend,
        store: Arc<SqliteStore>,
        providers: Arc<ProviderRegistry>,
    ) -> Result<Self> {
        let profile = RuntimeProfile::from_friend(&friend)?;
        let judge_delegate = if friend.judge_provider_ref.is_some() {
            Some(ApiAgent::new(friend.clone(), providers.clone())?)
        } else {
            None
        };
        Ok(Self {
            friend,
            profile,
            runtime: Arc::new(AgentRuntime::new(store, providers)),
            judge_delegate,
        })
    }

    pub fn runtime_profile(&self) -> &RuntimeProfile {
        &self.profile
    }
}

#[async_trait]
impl Agent for UnifiedAgent {
    fn kind(&self) -> AgentKind {
        match self.friend.backend_kind {
            crate::domain::BackendKind::Pty => AgentKind::Pty,
            crate::domain::BackendKind::Api => AgentKind::Api,
            crate::domain::BackendKind::Assistant => AgentKind::Assistant,
            crate::domain::BackendKind::Human => AgentKind::Human,
        }
    }

    async fn warmup(&self) -> Result<()> {
        Ok(())
    }

    async fn send(
        &self,
        ctx: ChatContext,
        prompt: String,
    ) -> Result<BoxStream<'static, AgentEvent>> {
        self.runtime
            .run_turn(&self.friend, &self.profile, &ctx, prompt)
            .await
    }

    async fn judge(&self, ctx: ChatContext, msg: &Message) -> Result<Judgment> {
        if let Some(api) = &self.judge_delegate {
            return api.judge(ctx, msg).await;
        }
        match self.friend.backend_kind {
            BackendKind::Assistant => Ok(Judgment {
                should_reply: true,
                confidence: 0.7,
                reason: Some("助理默认愿意参与".into()),
                suggested_delay_ms: 200,
            }),
            BackendKind::Pty => Ok(Judgment {
                should_reply: false,
                confidence: 0.0,
                reason: Some("CLI 好友默认不参与群聊 judge；可在好友配置 judge_provider_ref".into()),
                suggested_delay_ms: 0,
            }),
            _ => Ok(Judgment::default()),
        }
    }
}
