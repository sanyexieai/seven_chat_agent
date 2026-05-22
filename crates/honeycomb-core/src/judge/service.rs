use std::sync::Arc;

use honeycomb_judge::{
    resolve_effective_judge, HistoryLine, JudgeEngine, JudgeMember, JudgeRequest, Judgment,
    TriggerSenderKind,
};

use crate::domain::{Friend, GroupSettings, Message, SenderKind};
use crate::provider::ProviderRegistry;

use super::bridge::ProviderLlmJudgePort;

pub struct JudgeService {
    port: Arc<ProviderLlmJudgePort>,
}

impl JudgeService {
    pub fn new(providers: Arc<ProviderRegistry>) -> Self {
        Self {
            port: Arc::new(ProviderLlmJudgePort::new(providers)),
        }
    }

    pub async fn evaluate_member(
        &self,
        group: &GroupSettings,
        member: &Friend,
        member_judge_override: Option<&honeycomb_judge::MemberJudgeOverride>,
        history: &[Message],
        trigger: &Message,
    ) -> Judgment {
        let req = Self::build_request(group, member, member_judge_override, history, trigger);
        let env_provider = std::env::var("HONEYCOMB_JUDGE_PROVIDER").ok();
        let registry = Arc::clone(&self.port.providers);
        JudgeEngine::evaluate(
            &req,
            Some(self.port.as_ref()),
            env_provider.as_deref(),
            |id| registry.get(id).is_some(),
        )
        .await
    }

    fn build_request(
        group: &GroupSettings,
        member: &Friend,
        member_judge_override: Option<&honeycomb_judge::MemberJudgeOverride>,
        history: &[Message],
        trigger: &Message,
    ) -> JudgeRequest {
        let effective_judge =
            resolve_effective_judge(&group.judge, member_judge_override, None);
        JudgeRequest {
            group_judge: effective_judge,
            member: JudgeMember {
                id: member.id.clone(),
                name: member.name.clone(),
                personality: member.personality.clone(),
                focus_tags: member.focus_tags.clone(),
                judge_provider_ref: None,
            },
            trigger_sender: match trigger.sender_kind {
                SenderKind::User => TriggerSenderKind::User,
                SenderKind::Friend => TriggerSenderKind::Friend,
                SenderKind::System => TriggerSenderKind::System,
            },
            trigger_sender_id: trigger.sender_id.clone(),
            trigger_sender_name: trigger.sender_name.clone(),
            trigger_content: trigger.content.clone(),
            mentions: trigger.mentions.clone(),
            history: history
                .iter()
                .map(|m| HistoryLine {
                    sender_name: m.sender_name.clone(),
                    content: m.content.clone(),
                })
                .collect(),
            extra_group_prompt: group.extra_system_prompt.clone(),
        }
    }
}
