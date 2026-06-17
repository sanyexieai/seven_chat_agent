//! 代理人拍板后衔接专家执行：群聊与任务流共用一套判定与触发逻辑。

use super::assistant_delegate::DelegateTaskHint;
use super::task_flow::{TaskFlowCheckpoint, TaskFlowExecuteOutcome};
use super::{BusEvent, ExpertReplyMode, MessageDispatcher};
use crate::domain::{
    Conversation, Friend, Group, GroupSettings, Message, MessageStatus,
    TaskFlowResumeAfterDelegateMode,
};
use crate::Result;

/// 代理人发言前，本轮专家阶段的结束状态。
#[derive(Debug, Clone)]
pub(super) enum DelegatePriorOutcome {
    /// 普通群聊：专家轮次已结束，无任务流交付判定。
    GroupTurn,
    Delivered,
    Stalled,
    Incomplete,
}

/// 代理人拍板后是否自动衔接执行的策略（以群助理设置为准）。
#[derive(Debug, Clone)]
pub(super) struct DelegateContinuePolicy {
    pub enabled: bool,
    pub mode: TaskFlowResumeAfterDelegateMode,
}

#[derive(Debug, Clone)]
pub(super) struct DelegateContinueContext {
    pub prior_outcome: DelegatePriorOutcome,
    pub task_checkpoint: Option<TaskFlowCheckpoint>,
}

impl DelegateContinueContext {
    pub(super) fn group_turn() -> Self {
        Self {
            prior_outcome: DelegatePriorOutcome::GroupTurn,
            task_checkpoint: None,
        }
    }

    pub(super) fn from_task_flow(checkpoint: TaskFlowCheckpoint) -> Self {
        let prior_outcome = match checkpoint.outcome {
            TaskFlowExecuteOutcome::Delivered => DelegatePriorOutcome::Delivered,
            TaskFlowExecuteOutcome::Stalled => DelegatePriorOutcome::Stalled,
            TaskFlowExecuteOutcome::Incomplete => DelegatePriorOutcome::Incomplete,
        };
        Self {
            prior_outcome,
            task_checkpoint: Some(checkpoint),
        }
    }

    pub(super) fn delegate_task_hint(&self) -> DelegateTaskHint {
        match self.prior_outcome {
            DelegatePriorOutcome::GroupTurn | DelegatePriorOutcome::Delivered => {
                DelegateTaskHint::Unknown
            }
            DelegatePriorOutcome::Stalled => DelegateTaskHint::Stalled,
            DelegatePriorOutcome::Incomplete => DelegateTaskHint::Incomplete,
        }
    }
}

pub(super) fn resolve_delegate_continue_policy(settings: &GroupSettings) -> DelegateContinuePolicy {
    let enabled = settings.assistant.continue_after_delegate_enabled
        || settings.task_flow.resume_after_delegate_enabled;
    let mode = if settings.assistant.continue_after_delegate_mode
        != TaskFlowResumeAfterDelegateMode::default()
    {
        settings.assistant.continue_after_delegate_mode.clone()
    } else {
        settings.task_flow.resume_after_delegate_mode.clone()
    };
    DelegateContinuePolicy { enabled, mode }
}

fn prior_outcome_label(outcome: &DelegatePriorOutcome) -> &'static str {
    match outcome {
        DelegatePriorOutcome::GroupTurn => "group_turn",
        DelegatePriorOutcome::Delivered => "delivered",
        DelegatePriorOutcome::Stalled => "stalled",
        DelegatePriorOutcome::Incomplete => "incomplete",
    }
}

/// 从正文解析 @成员名，供代理人/负责人点名后写入 `mentions`。
pub(super) fn parse_at_mention_assignees(content: &str, agents: &[Friend]) -> Vec<(String, String)> {
    let mut out: Vec<(String, String)> = agents
        .iter()
        .filter(|a| content.contains(&format!("@{}", a.name)))
        .map(|a| (a.id.clone(), a.name.clone()))
        .collect();
    out.sort_by(|a, b| a.0.cmp(&b.0));
    out.dedup_by(|a, b| a.0 == b.0);
    out
}

pub(super) fn enrich_delegation_mentions(
    content: &str,
    agents: &[Friend],
    exclude_id: Option<&str>,
) -> Vec<String> {
    parse_at_mention_assignees(content, agents)
        .into_iter()
        .filter(|(id, _)| exclude_id.is_none_or(|x| x != id))
        .map(|(id, _)| id)
        .collect()
}

/// 成员可匹配别名：全名 + ASCII 前缀（如 `cursor本地` → `cursor`）。
fn member_name_aliases(name: &str) -> Vec<String> {
    let mut out = vec![name.to_string()];
    let ascii: String = name
        .chars()
        .take_while(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '-')
        .collect();
    if ascii.len() >= 2 && ascii != name {
        out.push(ascii);
    }
    out
}

const NEGATIVE_MENTION_MARKERS: &[&str] = &[
    "持续",
    "空消息",
    "发送失败",
    "失败",
    "障碍",
    "挂 Issue",
    "恢复后",
    "有障碍",
    "通道",
    "不挡",
];

fn mention_window_is_negative(content: &str, match_start: usize) -> bool {
    let tail = &content[match_start..];
    let window: String = tail.chars().take(48).collect();
    NEGATIVE_MENTION_MARKERS
        .iter()
        .any(|m| window.contains(m))
}

fn score_pattern(content: &str, pattern: &str, base: i32) -> i32 {
    content
        .find(pattern)
        .filter(|&pos| !mention_window_is_negative(content, pos))
        .map(|_| base)
        .unwrap_or(0)
}

/// 对成员在拍板正文中的「须执行」指派强度打分（越高越应调度）。
pub(super) fn delegate_assignment_score(content: &str, member: &Friend) -> i32 {
    let mut best = 0i32;
    for alias in member_name_aliases(&member.name) {
        best = best.max(score_pattern(content, &format!("@{alias}"), 100));
        for pat in [
            format!("**{alias}，"),
            format!("**{alias},"),
            format!("**{alias}**"),
            format!("**{alias} "),
            format!("{alias}，按"),
            format!("{alias},按"),
            format!("{alias} 负责"),
            format!("{alias}负责"),
            format!("{alias} 执行"),
            format!("{alias}执行"),
        ] {
            best = best.max(score_pattern(content, &pat, 95));
        }
        if alias == member.name {
            best = best.max(score_pattern(content, &member.name, 75));
        } else if alias.len() >= 3 {
            best = best.max(score_pattern(content, &alias, 70));
        }
    }
    best
}

/// 从代理人拍板正文解析须执行的成员（指派句式优先，过滤「codex 空消息」类被动提及）。
pub(super) fn resolve_delegate_targets(content: &str, members: &[Friend]) -> Vec<Friend> {
    let mut scored: Vec<(Friend, i32)> = members
        .iter()
        .map(|m| (m.clone(), delegate_assignment_score(content, m)))
        .filter(|(_, score)| *score > 0)
        .collect();
    if scored.is_empty() {
        return vec![];
    }
    scored.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.id.cmp(&b.0.id)));
    const DIRECTIVE_FLOOR: i32 = 90;
    if scored.iter().any(|(_, s)| *s >= DIRECTIVE_FLOOR) {
        scored.retain(|(_, s)| *s >= DIRECTIVE_FLOOR);
    }
    scored.into_iter().map(|(m, _)| m).collect()
}

impl MessageDispatcher {
    /// 用户回合收尾：助理综合 → 按统一策略衔接执行。
    pub(super) async fn finalize_group_user_turn(
        &self,
        conv: &Conversation,
        group: &Group,
        settings: &GroupSettings,
        user_msg: &Message,
        turn_id: &str,
        ctx: DelegateContinueContext,
    ) -> Result<()> {
        let assistant_reply = self
            .maybe_dispatch_group_assistant(
                &conv.id,
                group,
                user_msg,
                turn_id,
                super::assistant_delegate::GroupAssistantPhase::AfterExperts,
                ctx.delegate_task_hint(),
            )
            .await?;

        if assistant_reply.is_none() {
            tracing::info!(
                turn_id = %turn_id,
                prior_outcome = prior_outcome_label(&ctx.prior_outcome),
                "delegate: no assistant reply, skip continue"
            );
        }

        self.continue_after_delegate(
            conv,
            group,
            settings,
            user_msg,
            turn_id,
            &ctx,
            assistant_reply,
        )
        .await?;

        self.emit_group_public_if_updated(&conv.id, &group.id, turn_id, settings)
            .await;
        Ok(())
    }

    async fn should_continue_after_delegate(
        &self,
        settings: &GroupSettings,
        ctx: &DelegateContinueContext,
        assistant_reply: &Message,
        user_task: &str,
    ) -> Result<bool> {
        if assistant_reply.content.trim().is_empty() {
            tracing::info!(turn_id = %assistant_reply.turn_id, "delegate: skip continue, empty assistant reply");
            return Ok(false);
        }
        if assistant_reply.status == MessageStatus::WaitingHuman {
            tracing::info!(
                turn_id = %assistant_reply.turn_id,
                "delegate: skip continue, assistant waiting_human"
            );
            return Ok(false);
        }

        let policy = resolve_delegate_continue_policy(settings);
        if !policy.enabled || policy.mode == TaskFlowResumeAfterDelegateMode::Off {
            tracing::info!(
                turn_id = %assistant_reply.turn_id,
                enabled = policy.enabled,
                mode = ?policy.mode,
                "delegate: skip continue, policy disabled"
            );
            return Ok(false);
        }

        if policy.mode == TaskFlowResumeAfterDelegateMode::IncompleteOnly
            && !matches!(
                ctx.prior_outcome,
                DelegatePriorOutcome::Incomplete | DelegatePriorOutcome::GroupTurn
            )
        {
            tracing::info!(
                turn_id = %assistant_reply.turn_id,
                prior_outcome = prior_outcome_label(&ctx.prior_outcome),
                "delegate: skip continue, incomplete_only policy"
            );
            return Ok(false);
        }

        if policy.mode == TaskFlowResumeAfterDelegateMode::NotDelivered {
            tracing::info!(
                turn_id = %assistant_reply.turn_id,
                prior_outcome = prior_outcome_label(&ctx.prior_outcome),
                "delegate: continue after assistant (not_delivered policy)"
            );
            return Ok(true);
        }

        let check = self
            .judge
            .check_delegate_resume(
                settings,
                user_task,
                prior_outcome_label(&ctx.prior_outcome),
                &assistant_reply.content,
                policy.enabled,
                policy.mode,
            )
            .await;
        let conf = check.confidence.unwrap_or(0.5);
        let ok = check.should_resume && conf >= 0.4;
        tracing::info!(
            turn_id = %assistant_reply.turn_id,
            should_resume = check.should_resume,
            confidence = conf,
            reason = ?check.reason,
            prior_outcome = prior_outcome_label(&ctx.prior_outcome),
            "delegate: resume check"
        );
        Ok(ok)
    }

    async fn continue_after_delegate(
        &self,
        conv: &Conversation,
        group: &Group,
        settings: &GroupSettings,
        user_msg: &Message,
        turn_id: &str,
        ctx: &DelegateContinueContext,
        assistant_reply: Option<Message>,
    ) -> Result<()> {
        let Some(reply) = assistant_reply else {
            return Ok(());
        };
        if !self
            .should_continue_after_delegate(settings, ctx, &reply, &user_msg.content)
            .await?
        {
            return Ok(());
        }

        tracing::info!(
            turn_id = %turn_id,
            prior_outcome = prior_outcome_label(&ctx.prior_outcome),
            has_checkpoint = ctx.task_checkpoint.is_some(),
            "delegate: continuing execution after assistant decision"
        );

        self.emit(BusEvent::TaskFlowPhase {
            conversation_id: conv.id.clone(),
            turn_id: turn_id.to_string(),
            phase: "execute".into(),
            detail: Some("代理人拍板：衔接专家执行".into()),
        });

        let peer_replies = self
            .run_expert_frontier_after_delegate(conv, group, settings, &reply, turn_id)
            .await?;
        tracing::info!(
            turn_id = %turn_id,
            peer_replies = peer_replies,
            "delegate: expert frontier after assistant"
        );

        if let Some(ref checkpoint) = ctx.task_checkpoint {
            if matches!(
                ctx.prior_outcome,
                DelegatePriorOutcome::Stalled | DelegatePriorOutcome::Incomplete
            ) {
                tracing::info!(
                    turn_id = %turn_id,
                    prior_outcome = prior_outcome_label(&ctx.prior_outcome),
                    "delegate: resuming task flow leader loop"
                );
                self.resume_task_flow_after_delegate(
                    conv,
                    user_msg,
                    turn_id,
                    settings,
                    checkpoint,
                    &reply.content,
                )
                .await?;
            }
        }
        Ok(())
    }

    /// 以代理人拍板消息为触发，调度专家接话（与任务流协作轮共用 mention 过滤）。
    async fn run_expert_frontier_after_delegate(
        &self,
        conv: &Conversation,
        group: &Group,
        settings: &GroupSettings,
        assistant_reply: &Message,
        turn_id: &str,
    ) -> Result<usize> {
        let members =
            super::assistant_delegate::expert_friends_for_group(&self.dispatch_store(), &group.id)
                .await?;
        let targets = resolve_delegate_targets(&assistant_reply.content, &members);
        let mut trigger = assistant_reply.clone();
        if !targets.is_empty() {
            trigger.mentions = targets.iter().map(|m| m.id.clone()).collect();
        }
        tracing::info!(
            turn_id = %turn_id,
            target_names = ?targets.iter().map(|m| m.name.as_str()).collect::<Vec<_>>(),
            "delegate: forced execute targets"
        );

        let mode = ExpertReplyMode::DelegateExecute;

        let mut frontier = vec![trigger];
        let mut reply_count = 0usize;
        while !frontier.is_empty() {
            let t = frontier.remove(0);
            let replies = self
                .dispatch_expert_round(conv, group, settings, &t, turn_id, mode)
                .await?;
            reply_count += replies.len();
            if settings.allow_agent_to_agent {
                frontier.extend(replies);
            }
        }
        Ok(reply_count)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::BackendKind;

    fn agent(id: &str, name: &str) -> Friend {
        Friend {
            id: id.into(),
            name: name.into(),
            avatar: None,
            system_prompt: String::new(),
            personality: None,
            focus_tags: vec![],
            backend_kind: BackendKind::Api,
            backend_config: serde_json::json!({}),
            judge_provider_ref: None,
            enabled: true,
            is_builtin: false,
            active_workspace_id: None,
            profile: None,
            created_at: chrono::Utc::now(),
        }
    }

    #[test]
    fn enrich_delegation_mentions_parses_at_names() {
        let agents = vec![agent("a", "Alice"), agent("b", "Bob")];
        let ids = enrich_delegation_mentions("@Bob 请实现", &agents, None);
        assert_eq!(ids, vec!["b"]);
    }

    #[test]
    fn resolve_delegate_targets_matches_name_without_at() {
        let agents = vec![agent("c", "codex"), agent("u", "cursor本地")];
        let got = resolve_delegate_targets("请 codex 扫描仓库并列出优化点", &agents);
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].id, "c");
    }

    #[test]
    fn resolve_delegate_targets_matches_cursor_alias_not_codex_status() {
        let agents = vec![agent("c", "codex"), agent("u", "cursor本地")];
        let content = "好，我代主人拍板。\n\n**cursor，按你的 Plan A 直接开 PR：** 合入 ci.yml。\n\n\
            **codex** 持续空消息，消息通道有障碍。他的任务挂 Issue，等他恢复后自行接力。";
        let got = resolve_delegate_targets(content, &agents);
        assert_eq!(got.len(), 1, "got {:?}", got.iter().map(|a| &a.name).collect::<Vec<_>>());
        assert_eq!(got[0].id, "u");
    }

    #[test]
    fn resolve_policy_enabled_if_either_assistant_or_task_flow() {
        let mut settings = GroupSettings::default();
        settings.assistant.continue_after_delegate_enabled = false;
        settings.task_flow.resume_after_delegate_enabled = true;
        let p = resolve_delegate_continue_policy(&settings);
        assert!(p.enabled);
    }
}
