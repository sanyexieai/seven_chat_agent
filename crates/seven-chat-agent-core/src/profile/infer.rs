use futures::StreamExt;
use serde::Deserialize;

use crate::domain::Friend;
use crate::profile::registry::{find_framework, find_type, list_frameworks};
use crate::profile::types::{FrameworkBinding, MemberProfile, ProfileAxes};
use crate::profile::{derive_axes_with, derive_routing_hints_with, normalize_profile_for_save_with};
use crate::provider::types::{ChatMessage, ProviderEvent};
use crate::provider::ProviderRegistry;
use crate::store::SqliteStore;
use crate::Result;

#[derive(Debug, Clone, Deserialize)]
pub struct ProfileInferRaw {
    pub frameworks: Vec<FrameworkBinding>,
    #[serde(default)]
    pub axes: ProfileAxes,
    #[serde(default)]
    pub reasoning: String,
}

#[derive(Debug, Clone)]
pub struct ProfileInferResult {
    pub profile: MemberProfile,
    pub reasoning: String,
}

pub async fn infer_member_profile(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    friend: &Friend,
) -> Result<ProfileInferResult> {
    let catalogs = store.all_profile_frameworks().await?;
    let type_catalog = build_type_catalog_prompt(&catalogs);
    let tags = friend.focus_tags.join("、");
    let personality = friend.personality.as_deref().unwrap_or("（未填）");
    let system_prompt_excerpt = truncate_chars(&friend.system_prompt, 400);

    let user_prompt = format!(
        "根据以下 Agent 人设信息，为其选择最合适的成员画像类型。\n\n\
         名字：{}\n性格/介绍：{}\n关注点：{}\n人设摘要：{}\n\n\
         可选类型目录：\n{type_catalog}\n\n\
         请输出 JSON：{{\"frameworks\":[{{\"id\":\"mbti_16\",\"type_code\":\"ENTJ\",\"source\":\"inferred\",\"confidence\":0.85}}],\
         \"axes\":{{}},\"reasoning\":\"一句话中文理由\"}}\n\
         frameworks 最多 2 条（mbti_16 与/或 agent_24）；type_code 必须来自目录。",
        friend.name, personality, tags, system_prompt_excerpt
    );

    let raw = match infer_llm_json(store, providers, &user_prompt).await {
        Ok(r) => r,
        Err(e) => {
            tracing::warn!(err = %e, "profile infer LLM failed, using heuristic");
            return Ok(heuristic_infer(friend));
        }
    };

    let parsed: ProfileInferRaw = serde_json::from_str(extract_json_object(&raw).unwrap_or(&raw))
        .unwrap_or_else(|_| heuristic_infer_raw(friend));

    let mut frameworks = sanitize_bindings(&parsed.frameworks, &catalogs);
    if frameworks.is_empty() {
        frameworks = heuristic_infer(friend).profile.frameworks;
    }

    let mut profile = MemberProfile {
        schema_version: 1,
        frameworks,
        axes: parsed.axes,
        use_derived_routing: true,
        ..MemberProfile::default()
    };
    normalize_profile_for_save_with(&mut profile, &catalogs);
    profile.routing_hints = derive_routing_hints_with(&profile, &catalogs);
    profile.axes = derive_axes_with(&profile, &catalogs);

    Ok(ProfileInferResult {
        profile,
        reasoning: parsed.reasoning,
    })
}

fn sanitize_bindings(
    bindings: &[FrameworkBinding],
    catalogs: &[crate::profile::types::ProfileFrameworkCatalog],
) -> Vec<FrameworkBinding> {
    bindings
        .iter()
        .filter_map(|b| {
            let fw = find_framework(catalogs, &b.id)?;
            let def = find_type(fw, &b.type_code)?;
            Some(FrameworkBinding {
                id: fw.id.clone(),
                type_code: def.type_code.clone(),
                source: "inferred".into(),
                confidence: b.confidence.clamp(0.0, 1.0),
            })
        })
        .take(2)
        .collect()
}

fn build_type_catalog_prompt(catalogs: &[crate::profile::types::ProfileFrameworkCatalog]) -> String {
    catalogs
        .iter()
        .map(|fw| {
            let types = fw
                .types
                .iter()
                .map(|t| t.type_code.as_str())
                .collect::<Vec<_>>()
                .join(", ");
            format!("{} (id={}): {}", fw.name, fw.id, types)
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn heuristic_infer_raw(friend: &Friend) -> ProfileInferRaw {
    let lower = format!(
        "{} {}",
        friend.personality.as_deref().unwrap_or(""),
        friend.system_prompt
    )
    .to_lowercase();
    let agent_type = if lower.contains("协调") || lower.contains("主持") || lower.contains("pm") {
        "主持·调和"
    } else if lower.contains("被动") || lower.contains("旁听") || lower.contains("按需") {
        "旁听·专精"
    } else if lower.contains("主动") || lower.contains("攻坚") || lower.contains("揽") {
        "攻坚·快反"
    } else {
        "工匠·专注"
    };
    ProfileInferRaw {
        frameworks: vec![
            FrameworkBinding {
                id: "agent_24".into(),
                type_code: agent_type.into(),
                source: "heuristic".into(),
                confidence: 0.55,
            },
        ],
        axes: ProfileAxes::default(),
        reasoning: "启发式：根据性格关键词匹配协作型".into(),
    }
}

fn heuristic_infer(friend: &Friend) -> ProfileInferResult {
    let raw = heuristic_infer_raw(friend);
    let catalogs: Vec<_> = list_frameworks().iter().cloned().collect();
    let frameworks = sanitize_bindings(&raw.frameworks, &catalogs);
    let mut profile = MemberProfile {
        schema_version: 1,
        frameworks,
        use_derived_routing: true,
        ..Default::default()
    };
    normalize_profile_for_save_with(&mut profile, &catalogs);
    ProfileInferResult {
        profile,
        reasoning: raw.reasoning,
    }
}

async fn infer_llm_json(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    user_prompt: &str,
) -> Result<String> {
    let (provider_id, model) = resolve_infer_target()?;
    let provider = providers
        .get(&provider_id)
        .ok_or_else(|| crate::Error::Config(format!("infer provider not found: {provider_id}")))?;
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
                    "你是 Agent 成员画像推断器。只输出一个 JSON 对象，不要 markdown。",
                ),
                ChatMessage::user(user_prompt),
            ],
            temperature: Some(0.3),
            top_p: None,
            max_tokens: Some(512),
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
    Ok(raw)
}

fn resolve_infer_target() -> Result<(String, String)> {
    if let (Ok(p), Ok(m)) = (
        std::env::var("SEVEN_CHAT_AGENT_ASSISTANT_PROVIDER"),
        std::env::var("SEVEN_CHAT_AGENT_ASSISTANT_MODEL"),
    ) {
        if !p.trim().is_empty() && !m.trim().is_empty() {
            return Ok((p, m));
        }
    }
    if let (Ok(p), Ok(m)) = (
        std::env::var("SEVEN_CHAT_AGENT_JUDGE_PROVIDER"),
        std::env::var("SEVEN_CHAT_AGENT_JUDGE_MODEL"),
    ) {
        if !p.trim().is_empty() && !m.trim().is_empty() {
            return Ok((p, m));
        }
    }
    Err(crate::Error::Config(
        "未配置推断 Provider（ASSISTANT 或 JUDGE 环境变量）".into(),
    ))
}

fn extract_json_object(raw: &str) -> Option<&str> {
    let start = raw.find('{')?;
    let end = raw.rfind('}')?;
    Some(&raw[start..=end])
}

fn truncate_chars(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        return s.to_string();
    }
    let mut out: String = s.chars().take(max).collect();
    out.push('…');
    out
}
