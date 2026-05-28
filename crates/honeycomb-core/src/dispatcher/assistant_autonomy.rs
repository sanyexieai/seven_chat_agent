//! 群助理自治等级：启发式 + 可选 LLM 分类。

use crate::domain::{AutonomyClassifier, AutonomyLevel, GroupAssistantSettings};
use crate::provider::ProviderRegistry;
use crate::provider::types::{ChatMessage, ProviderEvent};
use crate::store::SqliteStore;
use futures::StreamExt;

use super::assistant_delegate::classify_autonomy;

pub async fn classify_autonomy_for_message(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    settings: &GroupAssistantSettings,
    user_content: &str,
    group_name: &str,
) -> AutonomyLevel {
    let heuristic = classify_autonomy(user_content);
    match settings.autonomy_classifier {
        AutonomyClassifier::Heuristic => return heuristic,
        AutonomyClassifier::Llm => {
            return classify_autonomy_llm(
                store,
                providers,
                settings,
                user_content,
                group_name,
            )
            .await
            .unwrap_or(heuristic);
        }
        AutonomyClassifier::Auto => {
            if let Some(level) = classify_autonomy_llm(
                store,
                providers,
                settings,
                user_content,
                group_name,
            )
            .await
            {
                return level;
            }
            return heuristic;
        }
    }
}

async fn classify_autonomy_llm(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    settings: &GroupAssistantSettings,
    user_content: &str,
    group_name: &str,
) -> Option<AutonomyLevel> {
    let (provider_id, model) = resolve_classifier_target(settings)?;
    let provider = providers.get(&provider_id)?;
    let keys = store.list_provider_keys(Some(&provider_id)).await.ok()?;
    let api_key_id = keys
        .iter()
        .find(|k| k.status == "active")
        .map(|k| k.id.clone());

    let mut req = crate::provider::types::ChatRequest::new(
        &model,
        vec![
            ChatMessage::system(
                "你是群聊助理的自治等级分类器。根据用户消息判断代理人可自主决定的最高等级。\n\
                 只输出一个 JSON 对象：{\"level\":\"l0\"|\"l1\"|\"l2\"|\"l3\"|\"l4\",\"reason\":\"简短中文\"}\n\
                 l0=仅观察 l1=轻量代答 l2=小决策 l3=须用户确认 l4=禁止代决/高风险",
            ),
            ChatMessage::user(format!(
                "群名：{group_name}\n用户消息：\n{user_content}\n\n请分类。"
            )),
        ],
    );
    req.api_key_id = api_key_id;
    req.stream = false;
    req.response_format_json = true;
    req.max_tokens = Some(128);

    let mut stream = provider.chat(req).await.ok()?;
    let mut raw = String::new();
    while let Some(item) = stream.next().await {
        if let Ok(ProviderEvent::Token(t)) = item {
            raw.push_str(&t);
        }
    }
    parse_autonomy_json(&raw)
}

fn resolve_classifier_target(settings: &GroupAssistantSettings) -> Option<(String, String)> {
    if let (Some(p), Some(m)) = (
        settings.classifier_provider_id.as_deref(),
        settings.classifier_model.as_deref(),
    ) {
        if !p.is_empty() && !m.is_empty() {
            return Some((p.to_string(), m.to_string()));
        }
    }
    let p = std::env::var("HONEYCOMB_ASSISTANT_PROVIDER")
        .ok()
        .filter(|s| !s.trim().is_empty())?;
    let m = std::env::var("HONEYCOMB_ASSISTANT_MODEL")
        .ok()
        .filter(|s| !s.trim().is_empty())?;
    Some((p, m))
}

fn parse_autonomy_json(raw: &str) -> Option<AutonomyLevel> {
    let trimmed = raw.trim();
    let json_str = if let Some(start) = trimmed.find('{') {
        let end = trimmed.rfind('}')?;
        &trimmed[start..=end]
    } else {
        trimmed
    };
    let v: serde_json::Value = serde_json::from_str(json_str).ok()?;
    let level = v
        .get("level")
        .and_then(|x| x.as_str())
        .unwrap_or("")
        .to_lowercase();
    parse_level_str(&level)
}

fn parse_level_str(s: &str) -> Option<AutonomyLevel> {
    match s {
        "l0" | "0" => Some(AutonomyLevel::L0),
        "l1" | "1" => Some(AutonomyLevel::L1),
        "l2" | "2" => Some(AutonomyLevel::L2),
        "l3" | "3" => Some(AutonomyLevel::L3),
        "l4" | "4" => Some(AutonomyLevel::L4),
        _ => None,
    }
}
