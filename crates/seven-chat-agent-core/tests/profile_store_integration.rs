//! 画像 + SQLite 存储集成测试（无 LLM）。

use seven_chat_agent_core::domain::{BackendKind, GroupMemberConfig, GroupMemberRole, GroupSettings};
use seven_chat_agent_core::profile::types::{
    ExtensionFieldSchema, ExtensionsSchema, FrameworkBinding, MemberProfile, MemberProfileOverlay,
    ProfileFrameworkCatalog, ProfileTypeDefinition,
};
use seven_chat_agent_core::profile::{pick_coordinator, self_nomination_candidates};
use seven_chat_agent_core::store::friend::UpsertFriend;
use seven_chat_agent_core::store::group::UpsertGroup;
use seven_chat_agent_core::store::profile_framework::UpsertProfileFramework;
use seven_chat_agent_core::store::SqliteStore;
use seven_chat_agent_judge::InitiativeLevel;
use std::collections::HashMap;

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

async fn test_store() -> (tempfile::TempDir, SqliteStore) {
    let dir = tempfile::tempdir().expect("tempdir");
    let path = dir.path().join("profile_test.db");
    let url = format!("sqlite://{}?mode=rwc", path.display());
    let store = SqliteStore::connect(&url).await.expect("connect");
    store.migrate().await.expect("migrate");
    store.ensure_tenant().await.expect("tenant");
    (dir, store)
}

async fn insert_api_friend(store: &SqliteStore, id: &str, name: &str) {
    store
        .upsert_friend(UpsertFriend {
            id: Some(id.into()),
            name: name.into(),
            avatar: None,
            system_prompt: String::new(),
            personality: None,
            focus_tags: vec![],
            backend_kind: BackendKind::Api,
            backend_config: serde_json::json!({
                "provider_id": "openai_compat",
                "model": "gpt-4o-mini"
            }),
            judge_provider_ref: None,
            enabled: true,
        })
        .await
        .expect("upsert friend");
}

#[tokio::test]
async fn profile_overlay_persist_and_effective_summary() {
    let (_dir, store) = test_store().await;

    insert_api_friend(&store, "coord", "主持").await;
    insert_api_friend(&store, "passive", "被动").await;
    insert_api_friend(&store, "pro", "攻坚").await;

    store
        .upsert_friend_profile("coord", profile_agent24("主持·调和"))
        .await
        .expect("coord profile");
    store
        .upsert_friend_profile("passive", profile_agent24("旁听·专精"))
        .await
        .expect("passive profile");
    store
        .upsert_friend_profile("pro", profile_agent24("攻坚·快反"))
        .await
        .expect("pro profile");

    store
        .upsert_group(UpsertGroup {
            id: Some("g1".into()),
            name: "测试群".into(),
            avatar: None,
            settings: GroupSettings::default(),
            members: vec![
                GroupMemberConfig {
                    friend_id: "coord".into(),
                    role: GroupMemberRole::Member,
                    judge_override: None,
                    profile_overlay: None,
                    effective_profile: None,
                },
                GroupMemberConfig {
                    friend_id: "passive".into(),
                    role: GroupMemberRole::Member,
                    judge_override: None,
                    profile_overlay: Some(MemberProfileOverlay {
                        routing_hints: Some(seven_chat_agent_judge::RoutingHints {
                            initiative: InitiativeLevel::Passive,
                            ..Default::default()
                        }),
                        disabled_frameworks: vec![],
                    }),
                    effective_profile: None,
                },
                GroupMemberConfig {
                    friend_id: "pro".into(),
                    role: GroupMemberRole::Member,
                    judge_override: None,
                    profile_overlay: None,
                    effective_profile: None,
                },
            ],
            member_ids: vec![],
            member_bindings: vec![],
            workspaces: vec![],
        })
        .await
        .expect("upsert group");

    let mut configs = store.list_group_member_configs("g1").await.expect("configs");
    store
        .enrich_group_member_profiles(&mut configs)
        .await
        .expect("enrich");

    let passive = configs.iter().find(|c| c.friend_id == "passive").unwrap();
    let eff = passive.effective_profile.as_ref().expect("summary");
    assert_eq!(eff.initiative, InitiativeLevel::Passive);

    let catalogs = store.all_profile_frameworks().await.expect("catalogs");
    let friends: Vec<_> = store.list_friends().await.expect("friends");
    let agents: Vec<_> = friends
        .into_iter()
        .filter(|f| ["coord", "passive", "pro"].contains(&f.id.as_str()))
        .collect();
    let overlays: HashMap<String, MemberProfileOverlay> = configs
        .iter()
        .filter_map(|c| c.profile_overlay.clone().map(|o| (c.friend_id.clone(), o)))
        .collect();

    let coordinator = pick_coordinator(&agents, &overlays, &catalogs);
    assert_eq!(coordinator.map(|f| f.id.as_str()), Some("coord"));

    let nominees = self_nomination_candidates(&agents, &overlays, &catalogs);
    assert!(!nominees.iter().any(|f| f.id == "passive"));
    assert!(nominees.iter().any(|f| f.id == "pro"));
}

#[tokio::test]
async fn custom_framework_extensions_roundtrip() {
    let (_dir, store) = test_store().await;

    insert_api_friend(&store, "f1", "成员A").await;

    let mut props = HashMap::new();
    props.insert(
        "team_role".into(),
        ExtensionFieldSchema {
            r#type: "string".into(),
            enum_values: vec![serde_json::json!("lead"), serde_json::json!("support")],
            max_length: None,
        },
    );

    store
        .upsert_custom_profile_framework(UpsertProfileFramework {
            id: Some("team_roles".into()),
            name: "团队角色".into(),
            catalog: ProfileFrameworkCatalog {
                id: "team_roles".into(),
                name: "团队角色".into(),
                version: "1".into(),
                types: vec![ProfileTypeDefinition {
                    type_code: "执行".into(),
                    label_zh: "执行".into(),
                    axis_defaults: Default::default(),
                    default_routing_hints: Default::default(),
                    prompt_snippet: String::new(),
                }],
                extensions_schema: Some(ExtensionsSchema { properties: props }),
            },
        })
        .await
        .expect("framework");

    let mut profile = profile_agent24("工匠·专注");
    profile.frameworks.push(FrameworkBinding {
        id: "team_roles".into(),
        type_code: "执行".into(),
        source: "user_selected".into(),
        confidence: 1.0,
    });
    profile.extensions = serde_json::json!({ "team_role": "lead" });

    store
        .upsert_friend_profile("f1", profile)
        .await
        .expect("valid extensions");

    let friend = store.get_friend("f1").await.expect("get").expect("exists");
    assert_eq!(
        friend
            .profile
            .as_ref()
            .and_then(|p| p.extensions.get("team_role")),
        Some(&serde_json::json!("lead"))
    );

    let mut bad = profile_agent24("工匠·专注");
    bad.frameworks.push(FrameworkBinding {
        id: "team_roles".into(),
        type_code: "执行".into(),
        source: "user_selected".into(),
        confidence: 1.0,
    });
    bad.extensions = serde_json::json!({ "team_role": "invalid" });
    assert!(store.upsert_friend_profile("f1", bad).await.is_err());
}
