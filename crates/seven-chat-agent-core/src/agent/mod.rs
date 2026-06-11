pub mod api;
pub mod assistant;
pub mod human;
pub mod pty;
pub mod registry;

pub use registry::{AgentRegistry, StubAgent};

use std::sync::Arc;

use async_trait::async_trait;
use futures::stream::BoxStream;
use serde::{Deserialize, Serialize};

use crate::domain::{CliBlockDelta, Friend, GroupSettings, Message, MessageAttachment};
use crate::Result;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentKind {
    Pty,
    Api,
    Assistant,
    Human,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProviderUsageInfo {
    pub model: Option<String>,
    pub tokens_in: i64,
    pub tokens_out: i64,
}

#[derive(Debug, Clone)]
pub enum AgentEvent {
    Token(String),
    /// Codex `exec --json` 等 CLI 的结构化展示增量。
    CliDelta(CliBlockDelta),
    Thinking(String),
    Tool { name: String, payload: String },
    Done(ProviderUsageInfo),
    Error(String),
    WaitingHuman { estimated_ms: u64 },
}

pub use crate::judge::Judgment;

#[derive(Debug, Clone)]
pub struct ChatContext {
    pub conversation_id: String,
    /// 群聊时为群 `id`；私聊为 `None`。
    pub group_id: Option<String>,
    pub group_settings: Option<GroupSettings>,
    pub history: Vec<Message>,
    pub self_friend: Friend,
    pub peers: Vec<Friend>,
    /// 当前轮用户消息的附件（用于多模态）。
    pub user_attachments: Vec<MessageAttachment>,
    /// 群成员 binding 上的 local_path（relay/local 执行 cwd）。
    pub member_group_local_path: Option<String>,
    /// 本群共识底座（同轮 dispatch 内复用，避免重复查询）。
    pub group_public_baseline: Option<String>,
}

impl ChatContext {
    pub fn group_cli_workspace(&self) -> Option<&str> {
        self.group_settings
            .as_ref()
            .and_then(|g| g.cli_workspace.as_deref())
    }

    pub async fn with_member_binding(
        mut self,
        store: &crate::store::SqliteStore,
    ) -> crate::Result<Self> {
        if let Some(gid) = self.group_id.as_deref() {
            self.member_group_local_path = store
                .resolve_member_group_local_path(gid, &self.self_friend.id)
                .await?;
        }
        Ok(self)
    }
}

#[async_trait]
pub trait Agent: Send + Sync {
    fn kind(&self) -> AgentKind;
    async fn warmup(&self) -> Result<()> {
        Ok(())
    }
    async fn shutdown(&self) -> Result<()> {
        Ok(())
    }

    async fn send(
        &self,
        ctx: ChatContext,
        prompt: String,
    ) -> Result<BoxStream<'static, AgentEvent>>;

    async fn judge(&self, ctx: ChatContext, msg: &Message) -> Result<Judgment>;
}

pub type AgentHandle = Arc<dyn Agent>;
