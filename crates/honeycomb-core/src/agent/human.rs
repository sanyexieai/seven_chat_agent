use async_stream::stream;
use async_trait::async_trait;
use futures::stream::BoxStream;

use crate::agent::{Agent, AgentEvent, AgentKind, ChatContext, Judgment, ProviderUsageInfo};
use crate::domain::{Friend, Message};
use crate::Result;

pub struct HumanAgent {
    friend: Friend,
}

impl HumanAgent {
    pub fn new(friend: Friend) -> Self {
        Self { friend }
    }
}

#[async_trait]
impl Agent for HumanAgent {
    fn kind(&self) -> AgentKind {
        AgentKind::Human
    }

    async fn send(
        &self,
        _ctx: ChatContext,
        _prompt: String,
    ) -> Result<BoxStream<'static, AgentEvent>> {
        let name = self.friend.name.clone();
        let s = stream! {
            yield AgentEvent::WaitingHuman { estimated_ms: 0 };
            yield AgentEvent::Token(format!(
                "（{name} 是真人好友，需要他/她自己回复。正在等待对方上线。）"
            ));
            yield AgentEvent::Done(ProviderUsageInfo::default());
        };
        Ok(Box::pin(s))
    }

    async fn judge(&self, _ctx: ChatContext, _msg: &Message) -> Result<Judgment> {
        Ok(Judgment {
            should_reply: false,
            confidence: 0.0,
            reason: Some("真人成员不参与 judge".into()),
            suggested_delay_ms: 0,
            source: None,
        })
    }
}
