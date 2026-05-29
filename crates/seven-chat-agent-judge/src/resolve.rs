use crate::types::GroupJudgeSettings;

/// 解析 LLM judge 使用的 Provider / model（本群成员覆盖 → 群级 → 环境变量）。
pub fn resolve_llm_target(
    group: &GroupJudgeSettings,
    member_in_group_llm_provider: Option<&str>,
    env_provider: Option<&str>,
    registry_has: impl Fn(&str) -> bool,
) -> Option<LlmJudgeTarget> {
    let candidates: Vec<Option<&str>> = vec![
        member_in_group_llm_provider.filter(|s| !s.trim().is_empty()),
        group.llm.provider_id.as_deref().filter(|s| !s.trim().is_empty()),
        env_provider.filter(|s| !s.trim().is_empty()),
    ];
    for pid in candidates.into_iter().flatten() {
        if registry_has(pid) {
            let model = group
                .llm
                .model
                .as_deref()
                .filter(|s| !s.trim().is_empty())
                .map(str::to_string)
                .or_else(|| std::env::var("SEVEN_CHAT_AGENT_JUDGE_MODEL").ok());
            let api_key_id = group.llm.api_key_id.clone();
            return Some(LlmJudgeTarget {
                provider_id: pid.to_string(),
                model: model.unwrap_or_else(|| "gpt-4o-mini".into()),
                api_key_id,
            });
        }
    }
    None
}

#[derive(Debug, Clone)]
pub struct LlmJudgeTarget {
    pub provider_id: String,
    pub model: String,
    pub api_key_id: Option<String>,
}
