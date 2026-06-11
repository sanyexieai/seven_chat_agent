use seven_chat_agent_judge::{CoordinationLevel, InitiativeLevel, RoutingHints};

use crate::domain::Friend;
use crate::profile::registry::{find_framework, find_type, list_frameworks};
use crate::profile::types::{
    EffectiveMemberProfile, FrameworkBinding, MemberProfile, MemberProfileOverlay, ProfileAxes,
};

fn default_catalogs() -> Vec<crate::profile::types::ProfileFrameworkCatalog> {
    list_frameworks().iter().cloned().collect()
}

/// 从 frameworks 合并推导 routing_hints 与 axes。
pub fn derive_routing_hints(profile: &MemberProfile) -> RoutingHints {
    derive_routing_hints_with(profile, &default_catalogs())
}

pub fn derive_routing_hints_with(
    profile: &MemberProfile,
    catalogs: &[crate::profile::types::ProfileFrameworkCatalog],
) -> RoutingHints {
    let mut hints = RoutingHints::default();
    let mut has_any = false;

    for binding in &profile.frameworks {
        if binding.id.is_empty() || binding.type_code.is_empty() {
            continue;
        }
        let Some(fw) = find_framework(catalogs, &binding.id) else {
            continue;
        };
        let Some(def) = find_type(fw, &binding.type_code) else {
            continue;
        };
        merge_routing_hints(&mut hints, &def.default_routing_hints);
        has_any = true;
    }

    if has_any {
        hints
    } else {
        RoutingHints::default()
    }
}

fn merge_routing_hints(target: &mut RoutingHints, add: &RoutingHints) {
    target.initiative = add.initiative;
    target.coordination = add.coordination;
    if add.respond_to_mention {
        target.respond_to_mention = true;
    }
    if add.self_nominate.is_some() {
        target.self_nominate = add.self_nominate;
    }
    if add.campaign_eligible.is_some() {
        target.campaign_eligible = add.campaign_eligible;
    }
    if add.fallback_pick_eligible.is_some() {
        target.fallback_pick_eligible = add.fallback_pick_eligible;
    }
    if !add.peer_vote_eligible {
        target.peer_vote_eligible = false;
    }
}

pub fn derive_axes(profile: &MemberProfile) -> ProfileAxes {
    derive_axes_with(profile, &default_catalogs())
}

pub fn derive_axes_with(
    profile: &MemberProfile,
    catalogs: &[crate::profile::types::ProfileFrameworkCatalog],
) -> ProfileAxes {
    let mut axes = profile.axes.clone();
    for binding in &profile.frameworks {
        let Some(fw) = find_framework(catalogs, &binding.id) else {
            continue;
        };
        let Some(def) = find_type(fw, &binding.type_code) else {
            continue;
        };
        merge_axes(&mut axes, &def.axis_defaults);
    }
    axes
}

fn merge_axes(target: &mut ProfileAxes, add: &ProfileAxes) {
    macro_rules! merge_f {
        ($field:ident) => {
            if add.$field.is_some() {
                target.$field = add.$field;
            }
        };
    }
    merge_f!(extraversion);
    merge_f!(intuition);
    merge_f!(thinking);
    merge_f!(judging);
    merge_f!(initiative);
    merge_f!(coordination);
}

pub fn build_persona_block(frameworks: &[FrameworkBinding]) -> String {
    build_persona_block_with(frameworks, &default_catalogs())
}

pub fn build_persona_block_with(
    frameworks: &[FrameworkBinding],
    catalogs: &[crate::profile::types::ProfileFrameworkCatalog],
) -> String {
    let mut parts = Vec::new();
    for binding in frameworks {
        let Some(fw) = find_framework(catalogs, &binding.id) else {
            continue;
        };
        let Some(def) = find_type(fw, &binding.type_code) else {
            continue;
        };
        if def.prompt_snippet.is_empty() {
            continue;
        }
        parts.push(format!("[{}·{}] {}", fw.name, def.label_zh, def.prompt_snippet));
    }
    parts.join("\n")
}

/// 协调者 prompt 用：本群成员能力一览。
fn initiative_label(l: InitiativeLevel) -> &'static str {
    match l {
        InitiativeLevel::Proactive => "主动",
        InitiativeLevel::Balanced => "均衡",
        InitiativeLevel::Passive => "被动",
    }
}

fn coordination_label(l: CoordinationLevel) -> &'static str {
    match l {
        CoordinationLevel::Coordinator => "协调",
        CoordinationLevel::Contributor => "协作",
        CoordinationLevel::None => "执行",
    }
}

pub fn build_member_roster(members: &[(&Friend, EffectiveMemberProfile)]) -> String {
    build_member_roster_with_hints(members, &std::collections::HashMap::new())
}

/// `capability_hints`: 成员 friend_id → 近期群表现摘要（可选）。
pub fn build_member_roster_with_hints(
    members: &[(&Friend, EffectiveMemberProfile)],
    capability_hints: &std::collections::HashMap<String, String>,
) -> String {
    members
        .iter()
        .map(|(f, eff)| {
            let mut tag_parts: Vec<String> = f.focus_tags.clone();
            if let Some(hint) = capability_hints.get(&f.id) {
                if !hint.trim().is_empty() {
                    tag_parts.push(hint.trim().to_string());
                }
            }
            if tag_parts.is_empty() {
                tag_parts = eff.capability_tags.clone();
            }
            let tags = tag_parts.join("、");
            let labels = framework_labels(&eff.frameworks).join("；");
            format!(
                "- {}（id={}）专长：{}；画像：{}；协作：{}/{}",
                f.name,
                f.id,
                if tags.is_empty() { "（未填）" } else { &tags },
                if labels.is_empty() { "默认" } else { &labels },
                initiative_label(eff.initiative),
                coordination_label(eff.coordination)
            )
        })
        .collect::<Vec<_>>()
        .join("\n")
}

pub fn framework_labels(frameworks: &[FrameworkBinding]) -> Vec<String> {
    framework_labels_with(frameworks, &default_catalogs())
}

pub fn framework_labels_with(
    frameworks: &[FrameworkBinding],
    catalogs: &[crate::profile::types::ProfileFrameworkCatalog],
) -> Vec<String> {
    frameworks
        .iter()
        .filter_map(|b| {
            let fw = find_framework(catalogs, &b.id)?;
            let def = find_type(fw, &b.type_code)?;
            Some(format!("{} {}", fw.name, def.label_zh))
        })
        .collect()
}

/// 合并好友基底、群 overlay，产出调度用有效画像。
pub fn resolve_effective_profile(
    friend: &Friend,
    base: Option<&MemberProfile>,
    overlay: Option<&MemberProfileOverlay>,
) -> EffectiveMemberProfile {
    resolve_effective_profile_with(friend, base, overlay, &default_catalogs())
}

pub fn resolve_effective_profile_with(
    friend: &Friend,
    base: Option<&MemberProfile>,
    overlay: Option<&MemberProfileOverlay>,
    catalogs: &[crate::profile::types::ProfileFrameworkCatalog],
) -> EffectiveMemberProfile {
    let mut profile = base.cloned().unwrap_or_default();
    if profile.use_derived_routing {
        profile.routing_hints = derive_routing_hints_with(&profile, catalogs);
    }

    let mut hints = profile.routing_hints.clone();
    if let Some(ov) = overlay {
        if let Some(ref ov_hints) = ov.routing_hints {
            merge_routing_hints(&mut hints, ov_hints);
        }
        if !ov.disabled_frameworks.is_empty() {
            profile.frameworks.retain(|f| !ov.disabled_frameworks.contains(&f.id));
        }
    }

    let frameworks = profile.frameworks.clone();
    EffectiveMemberProfile {
        routing_hints: hints.clone(),
        prompt_persona_block: build_persona_block_with(&frameworks, catalogs),
        capability_tags: friend.focus_tags.clone(),
        frameworks,
        initiative: hints.initiative,
        coordination: hints.coordination,
    }
}

/// 保存前：若开启推导则刷新 routing_hints。
pub fn normalize_profile_for_save(mut profile: MemberProfile) -> MemberProfile {
    normalize_profile_for_save_with(&mut profile, &default_catalogs());
    profile
}

pub fn normalize_profile_for_save_with(
    profile: &mut MemberProfile,
    catalogs: &[crate::profile::types::ProfileFrameworkCatalog],
) {
    if profile.use_derived_routing {
        profile.routing_hints = derive_routing_hints_with(profile, catalogs);
        profile.axes = derive_axes_with(profile, catalogs);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use seven_chat_agent_judge::{CoordinationLevel, InitiativeLevel};

    #[test]
    fn roster_includes_capability_hints() {
        use std::collections::HashMap;

        let f = Friend {
            id: "a1".into(),
            name: "Alice".into(),
            avatar: None,
            system_prompt: String::new(),
            personality: None,
            focus_tags: vec!["后端".into()],
            backend_kind: crate::domain::BackendKind::Api,
            backend_config: serde_json::json!({}),
            judge_provider_ref: None,
            enabled: true,
            is_builtin: false,
            active_workspace_id: None,
            profile: None,
            created_at: chrono::Utc::now(),
        };
        let eff = EffectiveMemberProfile {
            routing_hints: seven_chat_agent_judge::RoutingHints::default(),
            prompt_persona_block: String::new(),
            capability_tags: vec!["后端".into()],
            frameworks: vec![],
            initiative: InitiativeLevel::Balanced,
            coordination: CoordinationLevel::None,
        };
        let members = vec![(&f, eff)];
        let mut hints = HashMap::new();
        hints.insert("a1".into(), "上轮完成了 API 草案".into());
        let roster = build_member_roster_with_hints(&members, &hints);
        assert!(roster.contains("Alice"));
        assert!(roster.contains("API 草案"));
    }

    #[test]
    fn entj_derives_proactive_coordinator() {
        let profile = MemberProfile {
            frameworks: vec![FrameworkBinding {
                id: "mbti_16".into(),
                type_code: "ENTJ".into(),
                source: "user_selected".into(),
                confidence: 1.0,
            }],
            use_derived_routing: true,
            ..Default::default()
        };
        let hints = derive_routing_hints(&profile);
        assert_eq!(hints.initiative, InitiativeLevel::Proactive);
        assert_eq!(hints.coordination, CoordinationLevel::Coordinator);
    }

    #[test]
    fn overlay_passive_overrides_base() {
        let friend = Friend {
            id: "f1".into(),
            name: "A".into(),
            avatar: None,
            system_prompt: String::new(),
            personality: None,
            focus_tags: vec!["Rust".into()],
            backend_kind: crate::domain::BackendKind::Api,
            backend_config: serde_json::json!({}),
            judge_provider_ref: None,
            enabled: true,
            is_builtin: false,
            active_workspace_id: None,
            profile: None,
            created_at: chrono::Utc::now(),
        };
        let base = MemberProfile {
            frameworks: vec![FrameworkBinding {
                id: "mbti_16".into(),
                type_code: "ENTJ".into(),
                source: "user_selected".into(),
                confidence: 1.0,
            }],
            use_derived_routing: true,
            ..Default::default()
        };
        let overlay = MemberProfileOverlay {
            routing_hints: Some(RoutingHints {
                initiative: InitiativeLevel::Passive,
                ..RoutingHints::default()
            }),
            ..Default::default()
        };
        let eff = resolve_effective_profile(&friend, Some(&base), Some(&overlay));
        assert_eq!(eff.routing_hints.initiative, InitiativeLevel::Passive);
    }

    #[test]
    fn overlay_coordination_overrides_base() {
        use seven_chat_agent_judge::RoutingHints;
        let friend = Friend {
            id: "f1".into(),
            name: "A".into(),
            avatar: None,
            system_prompt: String::new(),
            personality: None,
            focus_tags: vec![],
            backend_kind: crate::domain::BackendKind::Api,
            backend_config: serde_json::json!({}),
            judge_provider_ref: None,
            enabled: true,
            is_builtin: false,
            active_workspace_id: None,
            profile: None,
            created_at: chrono::Utc::now(),
        };
        let base = MemberProfile {
            frameworks: vec![FrameworkBinding {
                id: "agent_24".into(),
                type_code: "工匠·专注".into(),
                source: "user_selected".into(),
                confidence: 1.0,
            }],
            use_derived_routing: true,
            ..Default::default()
        };
        let overlay = MemberProfileOverlay {
            routing_hints: Some(RoutingHints {
                coordination: CoordinationLevel::Coordinator,
                ..RoutingHints::default()
            }),
            ..Default::default()
        };
        let eff = resolve_effective_profile(&friend, Some(&base), Some(&overlay));
        assert_eq!(eff.coordination, CoordinationLevel::Coordinator);
    }
}
