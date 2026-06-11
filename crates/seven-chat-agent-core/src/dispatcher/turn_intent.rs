use futures::StreamExt;

use crate::domain::{GroupSettings, IntentClassifier, Message};
use crate::provider::types::{ChatMessage, ProviderEvent};
use crate::provider::ProviderRegistry;
use crate::store::SqliteStore;
use crate::Result;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum TurnIntent {
    Chitchat,
    Qa,
    Task,
    Decision,
    Status,
}

impl TurnIntent {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Chitchat => "chitchat",
            Self::Qa => "qa",
            Self::Task => "task",
            Self::Decision => "decision",
            Self::Status => "status",
        }
    }

    /// 是否进入群任务流（task / decision / status）。
    pub fn enters_task_flow(self) -> bool {
        matches!(self, Self::Task | Self::Decision | Self::Status)
    }

    fn parse_str(s: &str) -> Option<Self> {
        match s.trim().to_lowercase().as_str() {
            "chitchat" | "chat" => Some(Self::Chitchat),
            "qa" | "question" => Some(Self::Qa),
            "task" => Some(Self::Task),
            "decision" => Some(Self::Decision),
            "status" => Some(Self::Status),
            _ => None,
        }
    }
}

/// 当前群设置与用户意图是否应走任务流（不含 LLM 竞选等后续步骤）。
pub(super) fn should_enter_group_task_flow(
    settings: &GroupSettings,
    sender_kind: crate::domain::SenderKind,
    intent: TurnIntent,
) -> bool {
    sender_kind == crate::domain::SenderKind::User
        && settings.task_flow.enabled
        && intent.enters_task_flow()
}

/// 轻量启发式回合意图（P1；后续可接 LLM）。
pub(super) fn classify_turn_intent_heuristic(user_msg: &Message) -> TurnIntent {
    classify_content_heuristic(user_msg.content.trim())
}

fn classify_content_heuristic(content: &str) -> TurnIntent {
    let lower = content.to_lowercase();

    if is_status_like(&lower) {
        return TurnIntent::Status;
    }
    if is_decision_like(&lower) {
        return TurnIntent::Decision;
    }
    if is_task_like(&lower) {
        return TurnIntent::Task;
    }
    if is_qa_like(content, &lower) {
        return TurnIntent::Qa;
    }
    TurnIntent::Chitchat
}

pub(super) async fn classify_turn_intent(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    settings: &GroupSettings,
    user_msg: &Message,
) -> TurnIntent {
    match settings.orchestration.intent_classifier {
        IntentClassifier::Heuristic => classify_turn_intent_heuristic(user_msg),
        IntentClassifier::Llm => classify_turn_intent_llm(store, providers, user_msg)
            .await
            .unwrap_or_else(|e| {
                tracing::warn!(err = %e, "turn_intent LLM failed, fallback heuristic");
                classify_turn_intent_heuristic(user_msg)
            }),
        IntentClassifier::Auto => {
            if let Ok(intent) = classify_turn_intent_llm(store, providers, user_msg).await {
                return intent;
            }
            classify_turn_intent_heuristic(user_msg)
        }
    }
}

async fn classify_turn_intent_llm(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    user_msg: &Message,
) -> Result<TurnIntent> {
    let (provider_id, model) = resolve_intent_target()?;
    let provider = providers
        .get(&provider_id)
        .ok_or_else(|| crate::Error::Config(format!("intent provider not found: {provider_id}")))?;
    let keys = store.list_provider_keys(Some(&provider_id)).await?;
    let api_key_id = keys
        .iter()
        .find(|k| k.status == "active")
        .map(|k| k.id.clone());

    let mut stream = provider
        .chat(crate::provider::types::ChatRequest {
            model,
            api_key_id,
            messages: vec![
                ChatMessage::system(
                    "你是群聊回合意图分类器。只输出 JSON：{\"intent\":\"chitchat\"|\"qa\"|\"task\"|\"decision\"|\"status\",\"reason\":\"简短中文\"}",
                ),
                ChatMessage::user(format!("用户消息：\n{}", user_msg.content)),
            ],
            temperature: Some(0.2),
            top_p: None,
            max_tokens: Some(96),
            stream: false,
            response_format_json: true,
        })
        .await?;

    let mut raw = String::new();
    while let Some(item) = stream.next().await {
        if let Ok(ProviderEvent::Token(t)) = item {
            raw.push_str(&t);
        }
    }
    let json_str = raw
        .find('{')
        .and_then(|s| raw.rfind('}').map(|e| &raw[s..=e]))
        .unwrap_or(raw.trim());
    let v: serde_json::Value = serde_json::from_str(json_str)
        .map_err(|e| crate::Error::Config(format!("intent JSON parse: {e}")))?;
    let intent_str = v
        .get("intent")
        .and_then(|x| x.as_str())
        .unwrap_or("chitchat");
    Ok(TurnIntent::parse_str(intent_str).unwrap_or(TurnIntent::Chitchat))
}

fn resolve_intent_target() -> Result<(String, String)> {
    if let (Ok(p), Ok(m)) = (
        std::env::var("SEVEN_CHAT_AGENT_JUDGE_PROVIDER"),
        std::env::var("SEVEN_CHAT_AGENT_JUDGE_MODEL"),
    ) {
        if !p.trim().is_empty() && !m.trim().is_empty() {
            return Ok((p, m));
        }
    }
    if let (Ok(p), Ok(m)) = (
        std::env::var("SEVEN_CHAT_AGENT_ASSISTANT_PROVIDER"),
        std::env::var("SEVEN_CHAT_AGENT_ASSISTANT_MODEL"),
    ) {
        if !p.trim().is_empty() && !m.trim().is_empty() {
            return Ok((p, m));
        }
    }
    Err(crate::Error::Config(
        "未配置意图分类 Provider（JUDGE 或 ASSISTANT 环境变量）".into(),
    ))
}

fn is_status_like(lower: &str) -> bool {
    [
        "进度", "进展", "完成了吗", "搞定了吗", "怎么样了", "status", "done yet",
    ]
    .iter()
    .any(|k| lower.contains(k))
}

fn is_decision_like(lower: &str) -> bool {
    ["选型", "选哪个", "是否", "要不要", "对比", "哪个好", "建议用"]
        .iter()
        .any(|k| lower.contains(k))
        || (lower.contains("还是") && (lower.contains('?') || lower.contains('？')))
}

fn is_task_like(lower: &str) -> bool {
    [
        "实现", "修复", "fix", "implement", "重构", "refactor", "部署", "deploy", "上线",
        "开发", "编写", "执行", "运行", "cargo ", "npm ", "创建", "添加功能", "bug", "issue",
        "任务", "负责",
    ]
    .iter()
    .any(|k| lower.contains(k))
}

fn is_qa_like(content: &str, lower: &str) -> bool {
    content.contains('?')
        || content.contains('？')
        || [
            "怎么", "如何", "为什么", "啥", "吗", "么", "哪", "谁", "多少",
        ]
        .iter()
        .any(|k| lower.contains(k))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::{MessageStatus, SenderKind};

    fn user_msg(content: &str) -> Message {
        Message {
            id: "m1".into(),
            conversation_id: "c".into(),
            turn_id: "t".into(),
            parent_id: None,
            sender_kind: SenderKind::User,
            sender_id: "u".into(),
            sender_name: "你".into(),
            content: content.into(),
            content_blocks: None,
            mentions: vec![],
            status: MessageStatus::Done,
            seen_by: vec![],
            model_used: None,
            tokens_in: None,
            tokens_out: None,
            on_behalf_of_user: false,
            workspace_id: None,
            attachments: vec![],
            created_at: chrono::Utc::now(),
        }
    }

    #[test]
    fn classifies_task() {
        assert_eq!(
            classify_turn_intent_heuristic(&user_msg("帮我 refactor 登录模块")),
            TurnIntent::Task
        );
    }

    #[test]
    fn classifies_chitchat() {
        assert_eq!(
            classify_turn_intent_heuristic(&user_msg("大家下午好")),
            TurnIntent::Chitchat
        );
    }

    #[test]
    fn classifies_decision() {
        assert_eq!(
            classify_turn_intent_heuristic(&user_msg("用 Redis 还是 Postgres 存会话？")),
            TurnIntent::Decision
        );
    }

    #[test]
    fn classifies_qa() {
        assert_eq!(
            classify_turn_intent_heuristic(&user_msg("什么是 async trait？")),
            TurnIntent::Qa
        );
    }

    #[test]
    fn chitchat_does_not_enter_task_flow() {
        use crate::domain::{GroupSettings, SenderKind};
        let mut s = GroupSettings::default();
        s.task_flow.enabled = true;
        let intent = classify_turn_intent_heuristic(&user_msg("大家下午好"));
        assert!(!should_enter_group_task_flow(&s, SenderKind::User, intent));
    }

    #[test]
    fn task_flow_disabled_falls_through_to_frontier() {
        use crate::domain::{GroupSettings, SenderKind};
        let s = GroupSettings::default();
        let intent = classify_turn_intent_heuristic(&user_msg("帮我 refactor 模块"));
        assert!(!should_enter_group_task_flow(&s, SenderKind::User, intent));
    }

    #[test]
    fn task_intent_enters_task_flow_when_enabled() {
        use crate::domain::{GroupSettings, SenderKind};
        let mut s = GroupSettings::default();
        s.task_flow.enabled = true;
        let intent = classify_turn_intent_heuristic(&user_msg("帮我 refactor 模块"));
        assert!(should_enter_group_task_flow(&s, SenderKind::User, intent));
    }

    #[test]
    fn pipeline_task_orchestration_excludes_passive_nominees() {
        use crate::domain::{BackendKind, GroupSettings, SenderKind};
        use crate::profile::types::{FrameworkBinding, MemberProfile};
        use crate::profile::{
            merge_task_assignments, pick_coordinator, self_nomination_candidates,
        };
        use std::collections::HashMap;

        fn agent(id: &str, name: &str, type_code: &str) -> crate::domain::Friend {
            crate::domain::Friend {
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
                profile: Some(MemberProfile {
                    frameworks: vec![FrameworkBinding {
                        id: "agent_24".into(),
                        type_code: type_code.into(),
                        source: "test".into(),
                        confidence: 1.0,
                    }],
                    use_derived_routing: true,
                    ..Default::default()
                }),
                created_at: chrono::Utc::now(),
            }
        }

        let mut settings = GroupSettings::default();
        settings.task_flow.enabled = true;
        let user = user_msg("请重构登录模块并写测试");
        let intent = classify_turn_intent_heuristic(&user);
        assert!(should_enter_group_task_flow(&settings, SenderKind::User, intent));

        let catalogs: Vec<_> = crate::profile::list_frameworks().iter().cloned().collect();
        let agents = vec![
            agent("p1", "被动甲", "旁听·专精"),
            agent("p2", "被动乙", "协作·配合"),
            agent("coord", "主持", "主持·调和"),
            agent("pro", "攻坚", "攻坚·快反"),
        ];
        let overlays = HashMap::new();
        let coordinator = pick_coordinator(&agents, &overlays, &catalogs).unwrap();
        assert_eq!(coordinator.id, "coord");

        let nominees = self_nomination_candidates(&agents, &overlays, &catalogs);
        assert!(!nominees.iter().any(|f| f.id == "p1" || f.id == "p2"));
        assert!(nominees.iter().any(|f| f.id == "pro"));

        let plan = "请 @攻坚 负责实现，@被动甲 仅在被点名时配合";
        let assignees: Vec<(String, String)> = agents
            .iter()
            .filter(|a| plan.contains(&format!("@{}", a.name)))
            .map(|a| (a.id.clone(), a.name.clone()))
            .collect();
        let (ids, names) =
            merge_task_assignments("pro", "攻坚", &assignees, &agents);
        assert!(ids.contains(&"pro".into()));
        assert!(names.iter().any(|n| n == "攻坚"));
    }
}
