use std::sync::Arc;

use async_stream::stream;
use async_trait::async_trait;
use dashmap::DashMap;
use futures::stream::BoxStream;

use crate::agent::human::HumanAgent;
use crate::agent::pty::PtyAgent;
use crate::agent::{Agent, AgentEvent, AgentHandle, AgentKind, ChatContext, Judgment};
use crate::domain::PtyBackendConfig;
use crate::friend_cli::{is_external_cli_preset, pty_preset_is_worker_bee};
use crate::runtime::UnifiedAgent;
use crate::domain::{BackendKind, Friend, Message};
use crate::judge::JudgeService;
use crate::provider::ProviderRegistry;
use crate::store::SqliteStore;
use crate::{Error, Result};

pub struct AgentRegistry {
    store: Arc<SqliteStore>,
    providers: Arc<ProviderRegistry>,
    judge: Arc<JudgeService>,
    handles: DashMap<String, AgentHandle>,
}

impl AgentRegistry {
    pub fn new(
        store: Arc<SqliteStore>,
        providers: Arc<ProviderRegistry>,
        judge: Arc<JudgeService>,
    ) -> Self {
        Self {
            store,
            providers,
            judge,
            handles: DashMap::new(),
        }
    }

    pub async fn get(&self, friend_id: &str) -> Result<AgentHandle> {
        if let Some(h) = self.handles.get(friend_id) {
            return Ok(h.clone());
        }
        let friend = self
            .store
            .get_friend(friend_id)
            .await?
            .ok_or_else(|| Error::not_found(format!("friend {friend_id}")))?;
        let handle = self.build(friend)?;
        self.handles.insert(friend_id.into(), handle.clone());
        Ok(handle)
    }

    pub fn invalidate(&self, friend_id: &str) {
        self.handles.remove(friend_id);
    }

    fn build(&self, friend: Friend) -> Result<AgentHandle> {
        match friend.backend_kind {
            BackendKind::Human => Ok(Arc::new(HumanAgent::new(friend))),
            BackendKind::Pty => {
                let cfg: PtyBackendConfig =
                    serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
                if is_external_cli_preset(&cfg) {
                    Ok(Arc::new(PtyAgent::new(
                        friend,
                        self.store.clone(),
                        self.providers.clone(),
                        self.judge.clone(),
                    )?))
                } else if pty_preset_is_worker_bee(&cfg) {
                    Ok(Arc::new(UnifiedAgent::new(
                        friend,
                        self.store.clone(),
                        self.providers.clone(),
                        self.judge.clone(),
                    )?))
                } else {
                    Err(Error::bad_request(
                        "好友未配置 CLI 预设：请编辑好友，选择 Codex CLI / Claude / Worker Bee 后保存",
                    ))
                }
            }
            BackendKind::Assistant | BackendKind::Api => Ok(Arc::new(UnifiedAgent::new(
                friend,
                self.store.clone(),
                self.providers.clone(),
                self.judge.clone(),
            )?)),
        }
    }
}

pub struct StubAgent {
    friend: Friend,
    note: String,
}

impl StubAgent {
    pub fn new(friend: Friend, note: impl Into<String>) -> Self {
        Self {
            friend,
            note: note.into(),
        }
    }
}

#[async_trait]
impl Agent for StubAgent {
    fn kind(&self) -> AgentKind {
        match self.friend.backend_kind {
            BackendKind::Pty => AgentKind::Pty,
            BackendKind::Assistant => AgentKind::Assistant,
            BackendKind::Human => AgentKind::Human,
            BackendKind::Api => AgentKind::Api,
        }
    }

    async fn send(
        &self,
        _ctx: ChatContext,
        prompt: String,
    ) -> Result<BoxStream<'static, AgentEvent>> {
        let name = self.friend.name.clone();
        let note = self.note.clone();
        let prompt = prompt;
        let s = stream! {
            let reply = format!(
                "（{name}）收到：「{}」。\n[占位回复] {note}",
                if prompt.chars().count() > 80 {
                    let mut t: String = prompt.chars().take(80).collect();
                    t.push('…');
                    t
                } else {
                    prompt.clone()
                }
            );
            for ch in reply.chars() {
                yield AgentEvent::Token(ch.to_string());
            }
            yield AgentEvent::Done(crate::agent::ProviderUsageInfo::default());
        };
        Ok(Box::pin(s))
    }

    async fn judge(&self, _ctx: ChatContext, _msg: &Message) -> Result<Judgment> {
        Ok(Judgment {
            should_reply: false,
            confidence: 0.0,
            reason: Some(self.note.clone()),
            suggested_delay_ms: 0,
            source: None,
        })
    }
}
