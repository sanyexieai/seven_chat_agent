use std::sync::Arc;

use async_trait::async_trait;
use futures::stream::BoxStream;

use crate::agent::{Agent, AgentEvent, AgentKind, ChatContext, Judgment};
use crate::judge::JudgeService;
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
    judge: Arc<JudgeService>,
}

impl UnifiedAgent {
    pub fn new(
        friend: Friend,
        store: Arc<SqliteStore>,
        providers: Arc<ProviderRegistry>,
        judge: Arc<JudgeService>,
    ) -> Result<Self> {
        let profile = RuntimeProfile::from_friend(&friend)?;
        Ok(Self {
            friend,
            profile,
            runtime: Arc::new(AgentRuntime::new(store, providers)),
            judge,
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
        let mut profile = self.profile.clone();
        profile.workspace_cwd = self.profile.workspace_for_context(&self.friend, &ctx)?;
        self.runtime
            .run_turn(&self.friend, &profile, &ctx, prompt)
            .await
    }

    async fn judge(&self, ctx: ChatContext, msg: &Message) -> Result<Judgment> {
        if let Some(settings) = ctx.group_settings.as_ref() {
            return Ok(self
                .judge
                .evaluate_member(settings, &self.friend, None, &ctx.history, msg, None, None)
                .await);
        }
        if matches!(self.friend.backend_kind, BackendKind::Assistant) {
            return Ok(Judgment {
                should_reply: true,
                confidence: 0.7,
                reason: Some("助理默认愿意参与".into()),
                suggested_delay_ms: 200,
                source: None,
            });
        }
        Ok(Judgment::default())
    }
}
