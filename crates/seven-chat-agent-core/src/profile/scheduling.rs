use std::collections::HashMap;

use seven_chat_agent_judge::CoordinationLevel;

use crate::domain::Friend;
use crate::profile::types::{EffectiveMemberProfile, MemberProfileOverlay};
use crate::profile::{resolve_effective_profile_with, ProfileFrameworkCatalog};

/// 从成员中选出协调者（coordination=coordinator，主动性最高者优先）。
pub fn pick_coordinator<'a>(
    agents: &'a [Friend],
    overlays: &HashMap<String, MemberProfileOverlay>,
    catalogs: &[ProfileFrameworkCatalog],
) -> Option<&'a Friend> {
    agents
        .iter()
        .filter(|f| {
            effective(f, overlays, catalogs).coordination == CoordinationLevel::Coordinator
        })
        .max_by_key(|f| {
            effective(f, overlays, catalogs)
                .routing_hints
                .initiative
                .rank()
        })
}

/// 合并协调者 @ 分配与负责人，去重后返回 (ids, names)。
pub fn merge_task_assignments(
    leader_id: &str,
    leader_name: &str,
    coordinator_assignees: &[(String, String)],
    agents: &[Friend],
) -> (Vec<String>, Vec<String>) {
    let mut ids: Vec<String> = coordinator_assignees
        .iter()
        .map(|(id, _)| id.clone())
        .collect();
    if !ids.iter().any(|id| id == leader_id) {
        ids.insert(0, leader_id.to_string());
    }
    ids.sort();
    ids.dedup();
    let names: Vec<String> = ids
        .iter()
        .filter_map(|id| {
            agents
                .iter()
                .find(|a| &a.id == id)
                .map(|a| a.name.clone())
                .or_else(|| {
                    if id == leader_id {
                        Some(leader_name.to_string())
                    } else {
                        coordinator_assignees
                            .iter()
                            .find(|(aid, _)| aid == id)
                            .map(|(_, n)| n.clone())
                    }
                })
        })
        .collect();
    (ids, names)
}

/// 应参与自荐/竞选的成员（campaign_eligible）。
pub fn self_nomination_candidates<'a>(
    agents: &'a [Friend],
    overlays: &HashMap<String, MemberProfileOverlay>,
    catalogs: &[ProfileFrameworkCatalog],
) -> Vec<&'a Friend> {
    agents
        .iter()
        .filter(|f| {
            effective(f, overlays, catalogs)
                .routing_hints
                .effective_campaign_eligible()
        })
        .collect()
}

fn effective(
    friend: &Friend,
    overlays: &HashMap<String, MemberProfileOverlay>,
    catalogs: &[ProfileFrameworkCatalog],
) -> EffectiveMemberProfile {
    resolve_effective_profile_with(
        friend,
        friend.profile.as_ref(),
        overlays.get(&friend.id),
        catalogs,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::BackendKind;
    use crate::profile::types::{FrameworkBinding, MemberProfile};
    use seven_chat_agent_judge::InitiativeLevel;

    fn friend(id: &str, name: &str, profile: Option<MemberProfile>) -> Friend {
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
            profile,
            created_at: chrono::Utc::now(),
        }
    }

    fn profile_agent24(type_code: &str) -> MemberProfile {
        MemberProfile {
            frameworks: vec![FrameworkBinding {
                id: "agent_24".into(),
                type_code: type_code.into(),
                source: "test".into(),
                confidence: 1.0,
            }],
            use_derived_routing: true,
            ..Default::default()
        }
    }

    #[test]
    fn pick_coordinator_prefers_host() {
        let catalogs: Vec<_> = crate::profile::list_frameworks().iter().cloned().collect();
        let agents = vec![
            friend("a", "被动", Some(profile_agent24("旁听·专精"))),
            friend("b", "协调", Some(profile_agent24("主持·调和"))),
            friend("c", "主动", Some(profile_agent24("攻坚·快反"))),
        ];
        let picked = pick_coordinator(&agents, &HashMap::new(), &catalogs);
        assert_eq!(picked.map(|f| f.id.as_str()), Some("b"));
    }

    #[test]
    fn self_nominate_excludes_passive() {
        let catalogs: Vec<_> = crate::profile::list_frameworks().iter().cloned().collect();
        let agents = vec![
            friend("p", "被动", Some(profile_agent24("旁听·专精"))),
            friend("a", "主动", Some(profile_agent24("攻坚·快反"))),
        ];
        let nominees = self_nomination_candidates(&agents, &HashMap::new(), &catalogs);
        assert_eq!(nominees.len(), 1);
        assert_eq!(nominees[0].id, "a");
    }

    #[test]
    fn merge_task_assignments_includes_leader() {
        let agents = vec![
            friend("c", "协调", Some(profile_agent24("主持·调和"))),
            friend("a", "Alice", Some(profile_agent24("攻坚·快反"))),
            friend("b", "Bob", Some(profile_agent24("工匠·专注"))),
        ];
        let coord = vec![("a".into(), "Alice".into()), ("b".into(), "Bob".into())];
        let (ids, names) = merge_task_assignments("c", "协调", &coord, &agents);
        assert_eq!(ids.len(), 3);
        assert!(ids.contains(&"c".into()));
        assert_eq!(names.len(), 3);
    }

    #[test]
    fn orchestration_scenario_coordinator_and_proactive_only() {
        let catalogs: Vec<_> = crate::profile::list_frameworks().iter().cloned().collect();
        let agents = vec![
            friend("pass1", "被动甲", Some(profile_agent24("旁听·专精"))),
            friend("pass2", "被动乙", Some(profile_agent24("协作·配合"))),
            friend("coord", "主持", Some(profile_agent24("主持·调和"))),
            friend("pro", "攻坚", Some(profile_agent24("攻坚·快反"))),
        ];
        let overlays = HashMap::new();
        let coordinator = pick_coordinator(&agents, &overlays, &catalogs);
        assert_eq!(coordinator.map(|f| f.id.as_str()), Some("coord"));
        let nominees = self_nomination_candidates(&agents, &overlays, &catalogs);
        assert!(nominees.len() >= 1);
        assert!(nominees.iter().any(|f| f.id == "pro"));
        assert!(!nominees.iter().any(|f| f.id.starts_with("pass")));
    }

    #[test]
    fn passive_initiative_level() {
        let catalogs: Vec<_> = crate::profile::list_frameworks().iter().cloned().collect();
        let f = friend("p", "被动", Some(profile_agent24("协作·配合")));
        let eff = effective(&f, &HashMap::new(), &catalogs);
        assert_eq!(eff.initiative, InitiativeLevel::Passive);
        assert!(!eff.routing_hints.effective_campaign_eligible());
    }
}
