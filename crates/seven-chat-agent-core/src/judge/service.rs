use std::sync::Arc;

use seven_chat_agent_judge::{
    build_election_prompt, parse_election_response, resolve_effective_judge, resolve_llm_target,
    HistoryLine, JudgeEngine, JudgeMember, JudgeRequest, Judgment, LlmJudgeInput, LlmJudgePort,
    LlmJudgeTarget, ELECTION_SYSTEM, TriggerSenderKind,
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

    pub fn provider_registry(&self) -> Arc<ProviderRegistry> {
        Arc::clone(&self.port.providers)
    }

    pub async fn evaluate_member(
        &self,
        group: &GroupSettings,
        member: &Friend,
        member_judge_override: Option<&seven_chat_agent_judge::MemberJudgeOverride>,
        history: &[Message],
        trigger: &Message,
    ) -> Judgment {
        let req = Self::build_request(group, member, member_judge_override, history, trigger);
        let env_provider = std::env::var("SEVEN_CHAT_AGENT_JUDGE_PROVIDER").ok();
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
        member_judge_override: Option<&seven_chat_agent_judge::MemberJudgeOverride>,
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

    /// 解析 Judge/选举/互投用的 LLM（群配置 model → Provider 默认模型 → 环境变量，避免误用 gpt-4o-mini 调 DeepSeek）。
    pub fn resolve_judge_llm_target(
        &self,
        group: &GroupSettings,
    ) -> std::result::Result<LlmJudgeTarget, String> {
        let env_provider = std::env::var("SEVEN_CHAT_AGENT_JUDGE_PROVIDER").ok();
        let registry = Arc::clone(&self.port.providers);
        let mut target = resolve_llm_target(
            &group.judge,
            None,
            env_provider.as_deref(),
            |id| registry.get(id).is_some(),
        )
        .ok_or_else(|| "未配置可用的 judge Provider".to_string())?;
        if let Some(m) = group
            .judge
            .llm
            .model
            .as_ref()
            .filter(|s| !s.trim().is_empty())
        {
            target.model = m.clone();
        } else if let Some(handle) = registry.get(&target.provider_id) {
            let desc = handle.descriptor();
            if let Some(dm) = desc.default_model.as_ref().filter(|s| !s.trim().is_empty()) {
                target.model = dm.clone();
            }
        }
        if target.model == "gpt-4o-mini" && target.provider_id == "deepseek" {
            target.model = "deepseek-v4-flash".into();
        }
        Ok(target)
    }

    /// 根据竞选发言选举本轮任务负责人（需群 judge 已配置可用 LLM Provider）。
    pub async fn elect_leader(
        &self,
        group: &GroupSettings,
        user_task: &str,
        pitches: &[(String, String, String)],
        candidate_ids: &[String],
        peer_vote_tally: Option<&str>,
    ) -> std::result::Result<(String, String, String, f32), String> {
        if pitches.is_empty() {
            return Err("无竞选发言，无法选举".into());
        }
        let target = self.resolve_judge_llm_target(group)?;
        let prompt = build_election_prompt(
            &group.judge,
            user_task,
            pitches,
            peer_vote_tally,
            group.extra_system_prompt.as_deref(),
        );
        let raw = self
            .port
            .as_ref()
            .complete_json(LlmJudgeInput {
                provider_id: target.provider_id,
                model: target.model,
                api_key_id: target.api_key_id,
                system: ELECTION_SYSTEM.into(),
                user_prompt: prompt,
                max_tokens: Some(512),
            })
            .await?;
        let parsed = parse_election_response(&raw).ok_or_else(|| {
            format!("选举结果解析失败，原始输出：{}", truncate_err(&raw, 400))
        })?;
        let mut leader_id = parsed.leader_id.trim().to_string();
        if !candidate_ids.iter().any(|id| id == &leader_id) {
            if let Some(name) = parsed.leader_name.as_deref() {
                if let Some(f) = pitches.iter().find(|(_, n, _)| n == name) {
                    leader_id = f.0.clone();
                }
            }
        }
        if !candidate_ids.iter().any(|id| id == &leader_id) {
            leader_id = pitches[0].0.clone();
        }
        let leader_name = pitches
            .iter()
            .find(|(id, _, _)| id == &leader_id)
            .map(|(_, n, _)| n.clone())
            .unwrap_or_else(|| parsed.leader_name.unwrap_or_else(|| leader_id.clone()));
        let reason = parsed
            .reason
            .unwrap_or_else(|| "选举 LLM 未给出理由".into());
        let confidence = parsed.confidence.unwrap_or(0.7).clamp(0.0, 1.0);
        Ok((leader_id, leader_name, reason, confidence))
    }

    /// 单成员对竞选互投（背书）。
    pub async fn cast_peer_vote(
        &self,
        group: &GroupSettings,
        voter_name: &str,
        voter_id: &str,
        user_task: &str,
        pitches: &[(String, String, String)],
    ) -> std::result::Result<(String, String), String> {
        use seven_chat_agent_judge::{build_peer_vote_prompt, parse_peer_vote_response, PEER_VOTE_SYSTEM};
        let target = self.resolve_judge_llm_target(group)?;
        let prompt = build_peer_vote_prompt(voter_name, voter_id, user_task, pitches);
        let raw = self
            .port
            .as_ref()
            .complete_json(LlmJudgeInput {
                provider_id: target.provider_id,
                model: target.model,
                api_key_id: target.api_key_id,
                system: PEER_VOTE_SYSTEM.into(),
                user_prompt: prompt,
                max_tokens: Some(256),
            })
            .await?;
        let parsed = parse_peer_vote_response(&raw)
            .ok_or_else(|| format!("互投解析失败: {}", truncate_err(&raw, 200)))?;
        let mut endorse_id = parsed.endorse_leader_id.trim().to_string();
        if endorse_id == voter_id {
            return Err("不能投给自己".into());
        }
        if !pitches.iter().any(|(id, _, _)| id == &endorse_id) {
            endorse_id = pitches
                .first()
                .map(|(id, _, _)| id.clone())
                .ok_or_else(|| "无候选人".to_string())?;
        }
        let reason = parsed.reason.unwrap_or_else(|| "互投".into());
        Ok((endorse_id, reason))
    }
}

fn truncate_err(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        return s.to_string();
    }
    let mut t: String = s.chars().take(max).collect();
    t.push('…');
    t
}
