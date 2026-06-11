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
use crate::cli_relay::RelayHub;
use crate::store::SqliteStore;
use crate::{Error, Result};

pub struct AgentRegistry {
    store: Arc<SqliteStore>,
    providers: Arc<ProviderRegistry>,
    judge: Arc<JudgeService>,
    cli_relay: Arc<RelayHub>,
    handles: DashMap<String, AgentHandle>,
}

impl AgentRegistry {
    pub fn new(
        store: Arc<SqliteStore>,
        providers: Arc<ProviderRegistry>,
        judge: Arc<JudgeService>,
        cli_relay: Arc<RelayHub>,
    ) -> Self {
        Self {
            store,
            providers,
            judge,
            cli_relay,
            handles: DashMap::new(),
        }
    }

    pub async fn get(&self, friend_id: &str) -> Result<AgentHandle> {
        let tenant_id = crate::tenant_context::active_tenant_or(self.store.tenant_id());
        let cache_key = format!("{tenant_id}:{friend_id}");
        if let Some(h) = self.handles.get(&cache_key) {
            return Ok(h.clone());
        }
        let scoped = self.store.for_tenant(&tenant_id);
        let friend = scoped
            .get_friend(friend_id)
            .await?
            .ok_or_else(|| Error::not_found(format!("friend {friend_id}")))?;
        let handle = self.build(friend, scoped)?;
        self.handles.insert(cache_key, handle.clone());
        Ok(handle)
    }

    pub fn invalidate(&self, friend_id: &str) {
        self.handles.remove(friend_id);
        let suffix = format!(":{friend_id}");
        self.handles.retain(|k, _| !k.ends_with(&suffix));
    }

    /// 集成测试用：注入固定 Agent 实现，跳过真实 Provider/CLI。
    pub fn inject_handle_for_test(&self, friend_id: &str, handle: AgentHandle) {
        let tenant_id = crate::tenant_context::active_tenant_or(self.store.tenant_id());
        let cache_key = format!("{tenant_id}:{friend_id}");
        self.handles.insert(cache_key, handle);
    }

    fn build(&self, friend: Friend, store: SqliteStore) -> Result<AgentHandle> {
        let store = Arc::new(store);
        match friend.backend_kind {
            BackendKind::Human => Ok(Arc::new(HumanAgent::new(friend))),
            BackendKind::Pty => {
                let cfg: PtyBackendConfig =
                    serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
                if is_external_cli_preset(&cfg) {
                    Ok(Arc::new(PtyAgent::new(
                        friend,
                        store,
                        self.providers.clone(),
                        self.judge.clone(),
                        self.cli_relay.clone(),
                    )?))
                } else if pty_preset_is_worker_bee(&cfg) {
                    Ok(Arc::new(UnifiedAgent::new(
                        friend,
                        store,
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
                store,
                self.providers.clone(),
                self.judge.clone(),
            )?)),
        }
    }
}

pub struct StubAgent {
    friend: Friend,
    note: String,
    fixed_reply: Option<String>,
    prompt_rules: Vec<(String, String)>,
}

impl StubAgent {
    pub fn new(friend: Friend, note: impl Into<String>) -> Self {
        Self {
            friend,
            note: note.into(),
            fixed_reply: None,
            prompt_rules: Vec::new(),
        }
    }

    /// 每次 `send` 固定返回该文本（用于协调者 @ 分工等 E2E）。
    pub fn with_fixed_reply(friend: Friend, reply: impl Into<String>) -> Self {
        Self {
            friend,
            note: String::new(),
            fixed_reply: Some(reply.into()),
            prompt_rules: Vec::new(),
        }
    }

    /// prompt 含某子串时返回对应文本（先匹配先生效）。
    pub fn with_prompt_rules(
        friend: Friend,
        rules: &[(&str, &str)],
        fallback_note: impl Into<String>,
    ) -> Self {
        Self {
            friend,
            note: fallback_note.into(),
            fixed_reply: None,
            prompt_rules: rules
                .iter()
                .map(|(k, v)| (k.to_string(), v.to_string()))
                .collect(),
        }
    }

    fn reply_for_prompt(&self, prompt: &str) -> String {
        if let Some(text) = &self.fixed_reply {
            return text.clone();
        }
        for (key, reply) in &self.prompt_rules {
            if prompt.contains(key) {
                return reply.clone();
            }
        }
        let name = self.friend.name.clone();
        let note = &self.note;
        format!(
            "（{name}）收到：「{}」。\n[占位回复] {note}",
            if prompt.chars().count() > 80 {
                let mut t: String = prompt.chars().take(80).collect();
                t.push('…');
                t
            } else {
                prompt.to_string()
            }
        )
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
        let reply = self.reply_for_prompt(&prompt);
        let s = stream! {
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
