//! Dispatcher 编排链路：SQLite 群设置 → 成员画像 → 启发式 Judge → Scheduler（无 LLM）。

use std::collections::HashMap;
use std::sync::Arc;

use seven_chat_agent_core::domain::{
    BackendKind, GroupMemberConfig, GroupMemberRole, GroupOrchestrationSettings, GroupSettings,
    IntentClassifier, Message, MessageStatus, SenderKind,
};
use seven_chat_agent_core::judge::JudgeService;
use seven_chat_agent_core::profile::types::{FrameworkBinding, MemberProfile, MemberProfileOverlay};
use seven_chat_agent_core::profile::{
    pick_coordinator, resolve_effective_profile, self_nomination_candidates,
};
use seven_chat_agent_core::provider::ProviderRegistry;
use seven_chat_agent_core::scheduler::{CandidateInfo, SpeakerScheduler};
use seven_chat_agent_core::store::friend::UpsertFriend;
use seven_chat_agent_core::store::group::UpsertGroup;
use seven_chat_agent_core::store::SqliteStore;
use seven_chat_agent_judge::JudgeMode;

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

async fn test_store() -> (tempfile::TempDir, Arc<SqliteStore>) {
    let dir = tempfile::tempdir().expect("tempdir");
    let path = dir.path().join("dispatcher_orch.db");
    let url = format!("sqlite://{}?mode=rwc", path.display());
    let store = Arc::new(SqliteStore::connect(&url).await.expect("connect"));
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

fn orchestration_group_settings() -> GroupSettings {
    let mut settings = GroupSettings::default();
    settings.judge.mode = JudgeMode::Heuristic;
    settings.task_flow.enabled = true;
    settings.orchestration = GroupOrchestrationSettings {
        intent_classifier: IntentClassifier::Heuristic,
        light_task_flow: true,
        group_memory_enabled: true,
    };
    settings
}

fn user_trigger(content: &str) -> Message {
    Message {
        id: "m1".into(),
        conversation_id: "c1".into(),
        turn_id: "t1".into(),
        parent_id: None,
        sender_kind: SenderKind::User,
        sender_id: "user".into(),
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

async fn seed_orchestration_group(store: &SqliteStore) {
    insert_api_friend(store, "passive", "被动甲").await;
    insert_api_friend(store, "pro", "攻坚").await;
    insert_api_friend(store, "coord", "主持").await;

    store
        .upsert_friend_profile("passive", profile_agent24("旁听·专精"))
        .await
        .expect("passive profile");
    store
        .upsert_friend_profile("pro", profile_agent24("攻坚·快反"))
        .await
        .expect("pro profile");
    store
        .upsert_friend_profile("coord", profile_agent24("主持·调和"))
        .await
        .expect("coord profile");

    store
        .upsert_group(UpsertGroup {
            id: Some("g-orch".into()),
            name: "编排测试群".into(),
            avatar: None,
            settings: orchestration_group_settings(),
            members: vec![
                GroupMemberConfig {
                    friend_id: "passive".into(),
                    role: GroupMemberRole::Member,
                    judge_override: None,
                    profile_overlay: None,
                    effective_profile: None,
                },
                GroupMemberConfig {
                    friend_id: "pro".into(),
                    role: GroupMemberRole::Member,
                    judge_override: None,
                    profile_overlay: None,
                    effective_profile: None,
                },
                GroupMemberConfig {
                    friend_id: "coord".into(),
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
}

#[tokio::test]
async fn group_light_task_flow_settings_roundtrip() {
    let (_dir, store) = test_store().await;
    seed_orchestration_group(&store).await;

    let group = store
        .get_group("g-orch")
        .await
        .expect("get")
        .expect("exists");
    assert!(group.settings.orchestration.light_task_flow);
    assert_eq!(
        group.settings.orchestration.intent_classifier,
        IntentClassifier::Heuristic
    );
    assert!(!group.settings.effective_peer_vote_enabled());
    assert!(!group.settings.effective_plan_review_enabled());
    assert!(group.settings.task_flow.enabled);
}

#[tokio::test]
async fn sqlite_profiles_to_judge_and_scheduler_pipeline() {
    let (_dir, store) = test_store().await;
    seed_orchestration_group(&store).await;

    let group = store.get_group("g-orch").await.expect("get").expect("exists");
    let settings = group.settings.clone();
    let mut member_configs = store
        .list_group_member_configs("g-orch")
        .await
        .expect("configs");
    store
        .enrich_group_member_profiles(&mut member_configs)
        .await
        .expect("enrich");

    let catalogs = store.all_profile_frameworks().await.expect("catalogs");
    let mut agents = Vec::new();
    let mut overlays: HashMap<String, MemberProfileOverlay> = HashMap::new();
    for cfg in &member_configs {
        if let Some(f) = store.get_friend(&cfg.friend_id).await.expect("friend") {
            agents.push(f);
        }
        if let Some(o) = cfg.profile_overlay.clone() {
            overlays.insert(cfg.friend_id.clone(), o);
        }
    }

    let coordinator = pick_coordinator(&agents, &overlays, &catalogs);
    assert_eq!(coordinator.map(|f| f.id.as_str()), Some("coord"));

    let nominees = self_nomination_candidates(&agents, &overlays, &catalogs);
    assert!(!nominees.iter().any(|f| f.id == "passive"));
    assert!(nominees.iter().any(|f| f.id == "pro"));

    let providers = Arc::new(ProviderRegistry::new(store.clone()).await.expect("providers"));
    let judge = JudgeService::new(providers);
    let trigger = user_trigger("请重构登录模块并写集成测试");
    let history: Vec<Message> = vec![];

    let mut candidates: Vec<CandidateInfo> = Vec::new();
    for friend in &agents {
        let overlay = overlays.get(&friend.id);
        let effective = resolve_effective_profile(friend, friend.profile.as_ref(), overlay);
        let judgment = judge
            .evaluate_member(&settings, friend, None, &history, &trigger, Some(&effective), None)
            .await;
        candidates.push(CandidateInfo {
            friend_id: friend.id.clone(),
            friend_name: friend.name.clone(),
            backend_kind: friend.backend_kind,
            judgment,
            fallback_pick_eligible: effective.routing_hints.effective_fallback_pick_eligible(),
            initiative_rank: effective.initiative.rank(),
        });
    }

    let passive = candidates.iter().find(|c| c.friend_id == "passive").unwrap();
    assert!(
        !passive.judgment.should_reply,
        "被动成员不应接未点名用户消息"
    );
    assert!(!passive.fallback_pick_eligible);

    let sched = SpeakerScheduler::new();
    let picked = sched.rank(
        "t1",
        &settings,
        &trigger,
        candidates,
        &HashMap::new(),
        false,
        &[],
    );
    assert!(!picked.iter().any(|d| d.friend_id == "passive"));
    assert!(picked.iter().any(|d| d.friend_id == "pro" || d.friend_id == "coord"));
}
