//! 群设置就绪检查：在保存群或加载群配置时暴露任务流/Judge 问题，避免任务执行时静默失败。

use serde::{Deserialize, Serialize};

use seven_chat_agent_judge::resolve_llm_target;

use crate::domain::{GroupMemberConfig, GroupSettings};
use crate::provider::ProviderRegistry;
use crate::runtime::provider_env::env_has_provider_key;
use crate::store::SqliteStore;
use crate::Result;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupTaskFlowReadiness {
    pub task_flow_enabled: bool,
    pub ready: bool,
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
    pub agent_member_count: u32,
    pub judge_provider_id: Option<String>,
    pub judge_model: Option<String>,
    pub judge_key_configured: bool,
}

pub async fn validate_group_task_flow_readiness(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    settings: &GroupSettings,
    member_friend_ids: &[String],
) -> Result<GroupTaskFlowReadiness> {
    let tf = &settings.task_flow;
    let mut errors = Vec::new();
    let mut warnings = Vec::new();

    let mut agent_member_count = 0u32;
    for id in member_friend_ids {
        let Some(f) = store.get_friend(id).await? else {
            warnings.push(format!("成员 {} 不存在，已忽略", id));
            continue;
        };
        if f.backend_kind != crate::domain::BackendKind::Human {
            agent_member_count += 1;
        }
    }

    if !tf.enabled {
        return Ok(GroupTaskFlowReadiness {
            task_flow_enabled: false,
            ready: true,
            errors,
            warnings,
            agent_member_count,
            judge_provider_id: None,
            judge_model: None,
            judge_key_configured: false,
        });
    }

    if agent_member_count == 0 {
        errors.push(
            "已开启任务流，但群内没有可执行任务的 Agent 成员（需至少一位非「人类」好友）".into(),
        );
    } else if agent_member_count < 2 && (tf.campaign_enabled || tf.peer_vote_enabled) {
        warnings.push(format!(
            "任务流含竞选/互投，建议至少 2 位 Agent；当前仅 {} 位",
            agent_member_count
        ));
    }

    let (judge_provider_id, judge_model, judge_key_configured) =
        check_judge_llm(store, providers, settings, &mut errors, &mut warnings).await?;

    let ready = errors.is_empty();
    Ok(GroupTaskFlowReadiness {
        task_flow_enabled: true,
        ready,
        errors,
        warnings,
        agent_member_count,
        judge_provider_id,
        judge_model,
        judge_key_configured,
    })
}

async fn check_judge_llm(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    settings: &GroupSettings,
    errors: &mut Vec<String>,
    warnings: &mut Vec<String>,
) -> Result<(Option<String>, Option<String>, bool)> {
    let env_provider = std::env::var("SEVEN_CHAT_AGENT_JUDGE_PROVIDER").ok();
    let provider_exists = |id: &str| providers.get(id).is_some();

    let mut target = match resolve_llm_target(
        &settings.judge,
        None,
        env_provider.as_deref(),
        provider_exists,
    ) {
        Some(t) => t,
        None => {
            errors.push(
                "任务流需要 Judge LLM：请在「群 Judge」中选择 Provider（或配置 SEVEN_CHAT_AGENT_JUDGE_PROVIDER 环境变量）"
                    .into(),
            );
            return Ok((None, None, false));
        }
    };

    if let Some(m) = settings
        .judge
        .llm
        .model
        .as_ref()
        .filter(|s| !s.trim().is_empty())
    {
        target.model = m.clone();
    } else if let Some(handle) = providers.get(&target.provider_id) {
        let desc = handle.descriptor();
        if let Some(dm) = desc.default_model.as_ref().filter(|s| !s.trim().is_empty()) {
            target.model = dm.clone();
        }
    }
    if target.model == "gpt-4o-mini" && target.provider_id == "deepseek" {
        target.model = "deepseek-v4-flash".into();
    }

    if target.model.trim().is_empty() {
        errors.push(format!(
            "任务流 Judge 未配置模型：请为 Provider「{}」填写模型，或确保该 Provider 有默认模型",
            target.provider_id
        ));
    }

    if !provider_exists(&target.provider_id) {
        errors.push(format!(
            "Judge Provider「{}」未在系统中注册，请先在设置中配置 Provider",
            target.provider_id
        ));
    }

    let provider_id = target.provider_id.clone();
    let model = target.model.clone();

    let key_ok = judge_api_key_available(store, settings, &provider_id).await?;
    if !key_ok {
        errors.push(format!(
            "Judge Provider「{}」没有可用的 API Key：请在设置中添加 Key，或配置环境变量 {}",
            provider_id,
            crate::runtime::provider_env::env_api_key_var(&provider_id)
        ));
    }

    if settings.judge.mode == seven_chat_agent_judge::JudgeMode::Heuristic {
        warnings.push(
            "群 Judge 模式为「启发式」，但任务流的竞选/互投/选举仍依赖 LLM；请确认上方 Provider 与 Key 可用"
                .into(),
        );
    }

    Ok((Some(provider_id), Some(model), key_ok))
}

async fn judge_api_key_available(
    store: &SqliteStore,
    settings: &GroupSettings,
    provider_id: &str,
) -> Result<bool> {
    if let Some(key_id) = settings
        .judge
        .llm
        .api_key_id
        .as_ref()
        .filter(|s| !s.trim().is_empty())
    {
        if let Some(k) = store.get_provider_key(key_id).await? {
            if k.status == "active" && k.provider_id == provider_id {
                return Ok(true);
            }
        }
    }
    if env_has_provider_key(provider_id) {
        return Ok(true);
    }
    let keys = store.list_provider_keys(Some(provider_id)).await?;
    Ok(keys.iter().any(|k| k.status == "active"))
}

/// 从 Upsert 请求解析成员 id 列表。
pub fn member_ids_from_upsert(
    members: &[GroupMemberConfig],
    legacy_member_ids: &[String],
) -> Vec<String> {
    if !members.is_empty() {
        members.iter().map(|m| m.friend_id.clone()).collect()
    } else {
        legacy_member_ids.to_vec()
    }
}

/// 参与专家调度（Judge / 任务流）的成员 id。
pub fn expert_member_ids_from_upsert(
    members: &[GroupMemberConfig],
    legacy_member_ids: &[String],
) -> Vec<String> {
    if !members.is_empty() {
        members
            .iter()
            .filter(|m| m.role.participates_in_expert_scheduling())
            .map(|m| m.friend_id.clone())
            .collect()
    } else {
        legacy_member_ids.to_vec()
    }
}
