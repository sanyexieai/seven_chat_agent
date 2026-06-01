pub mod api;
pub mod assistant;
pub mod human;
pub mod pty;
pub mod registry;

pub use registry::AgentRegistry;

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
}

impl ChatContext {
    pub fn group_cli_workspace(&self) -> Option<&str> {
        self.group_settings
            .as_ref()
            .and_then(|g| g.cli_workspace.as_deref())
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
