//! MessageDispatcher 全链路 E2E：StubAgent 注入，无真实 LLM。

use std::sync::Arc;
use std::time::Duration;

use seven_chat_agent_core::agent::{AgentRegistry, StubAgent};
use seven_chat_agent_core::cli_relay::RelayHub;
use seven_chat_agent_core::dispatcher::{BusEvent, MessageDispatcher};
use seven_chat_agent_core::domain::{
    BackendKind, GroupMemberConfig, GroupMemberRole, GroupOrchestrationSettings, GroupSettings,
    IntentClassifier, MessageStatus, SenderKind,
};
use seven_chat_agent_core::judge::JudgeService;
use seven_chat_agent_core::profile::types::{FrameworkBinding, MemberProfile};
use seven_chat_agent_core::provider::ProviderRegistry;
use seven_chat_agent_core::store::friend::UpsertFriend;
use seven_chat_agent_core::store::group::UpsertGroup;
use seven_chat_agent_core::store::provider::UpsertProviderKey;
use seven_chat_agent_core::store::SqliteStore;
use seven_chat_agent_judge::JudgeMode;
use tokio::sync::broadcast::error::TryRecvError;
use tokio::time::Instant;

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

fn e2e_group_settings(task_flow: bool) -> GroupSettings {
    let mut s = GroupSettings::default();
    s.judge.mode = JudgeMode::Heuristic;
    s.task_flow.enabled = task_flow;
    s.assistant.enabled = false;
    s.allow_agent_to_agent = false;
    s.max_replies_per_turn = 4;
    s.per_agent_max_per_turn = 2;
    s
}

fn e2e_light_task_flow_settings() -> GroupSettings {
    let mut s = e2e_group_settings(true);
    s.orchestration = GroupOrchestrationSettings {
        intent_classifier: IntentClassifier::Heuristic,
        light_task_flow: true,
        group_memory_enabled: true,
    };
    s.task_flow.plan_enabled = false;
    s.task_flow.require_clear_delivery = false;
    s.judge.llm.provider_id = Some("openai".into());
    s.judge.llm.model = Some("gpt-4o-mini".into());
    s.judge.llm.api_key_id = Some("e2e-judge-key".into());
    s
}

async fn seed_judge_api_key(store: &SqliteStore) {
    store
        .upsert_provider_key(UpsertProviderKey {
            id: Some("e2e-judge-key".into()),
            provider_id: "openai".into(),
            label: "e2e".into(),
            secret: Some("sk-e2e-test".into()),
            rpm_limit: None,
            tpm_limit: None,
            monthly_budget_usd: None,
        })
        .await
        .expect("judge key");
}

async fn test_store() -> (tempfile::TempDir, Arc<SqliteStore>) {
    let dir = tempfile::tempdir().expect("tempdir");
    let path = dir.path().join("dispatcher_e2e.db");
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

async fn seed_single_agent_group(store: &SqliteStore, task_flow: bool) -> String {
    insert_api_friend(store, "pro", "攻坚").await;
    store
        .upsert_friend_profile("pro", profile_agent24("攻坚·快反"))
        .await
        .expect("profile");

    store
        .upsert_group(UpsertGroup {
            id: Some("g-e2e".into()),
            name: "E2E 群".into(),
            avatar: None,
            settings: e2e_group_settings(task_flow),
            members: vec![GroupMemberConfig {
                friend_id: "pro".into(),
                role: GroupMemberRole::Member,
                judge_override: None,
                profile_overlay: None,
                effective_profile: None,
            }],
            member_ids: vec![],
            member_bindings: vec![],
            workspaces: vec![],
        })
        .await
        .expect("group");

    let conv = store
        .get_or_create_group_conversation("g-e2e")
        .await
        .expect("conv");
    conv.id
}

async fn build_dispatcher(store: Arc<SqliteStore>) -> MessageDispatcher {
    let providers = Arc::new(ProviderRegistry::new(store.clone()).await.expect("providers"));
    let judge = Arc::new(JudgeService::new(providers.clone()));
    let agents = Arc::new(AgentRegistry::new(
        store.clone(),
        providers.clone(),
        judge.clone(),
        RelayHub::new(),
    ));
    MessageDispatcher::new(store, agents, judge, providers)
}

fn drain_bus_events(rx: &mut tokio::sync::broadcast::Receiver<BusEvent>) -> Vec<BusEvent> {
    let mut out = Vec::new();
    loop {
        match rx.try_recv() {
            Ok(ev) => out.push(ev),
            Err(TryRecvError::Empty) => break,
            Err(TryRecvError::Lagged(_)) => continue,
            Err(TryRecvError::Closed) => break,
        }
    }
    out
}

async fn wait_and_drain_events(
    rx: &mut tokio::sync::broadcast::Receiver<BusEvent>,
) -> Vec<BusEvent> {
    tokio::time::sleep(Duration::from_millis(150)).await;
    drain_bus_events(rx)
}

async fn wait_for_turn_end(
    rx: &mut tokio::sync::broadcast::Receiver<BusEvent>,
    timeout_ms: u64,
) -> Vec<BusEvent> {
    let deadline = Instant::now() + Duration::from_millis(timeout_ms);
    let mut all = Vec::new();
    loop {
        all.extend(drain_bus_events(rx));
        if all.iter().any(|e| matches!(e, BusEvent::TurnEnded { .. })) {
            break;
        }
        if Instant::now() >= deadline {
            break;
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    all
}

async fn seed_light_task_flow_group(store: Arc<SqliteStore>, group_id: &str) -> String {
    let _providers = ProviderRegistry::new(store.clone())
        .await
        .expect("seed providers");
    seed_judge_api_key(store.as_ref()).await;
    insert_api_friend(store.as_ref(), "coord", "主持").await;
    insert_api_friend(store.as_ref(), "pro", "攻坚").await;
    insert_api_friend(store.as_ref(), "passive", "被动").await;
    store
        .upsert_friend_profile("coord", profile_agent24("主持·调和"))
        .await
        .expect("coord profile");
    store
        .upsert_friend_profile("pro", profile_agent24("攻坚·快反"))
        .await
        .expect("pro profile");
    store
        .upsert_friend_profile("passive", profile_agent24("旁听·专精"))
        .await
        .expect("passive profile");

    store
        .upsert_group(UpsertGroup {
            id: Some(group_id.into()),
            name: "轻量任务流 E2E".into(),
            avatar: None,
            settings: e2e_light_task_flow_settings(),
            members: vec![
                GroupMemberConfig {
                    friend_id: "coord".into(),
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
                    friend_id: "passive".into(),
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
        .expect("group");

    store
        .get_or_create_group_conversation(group_id)
        .await
        .expect("conv")
        .id
}

async fn inject_light_task_flow_stubs(dispatcher: &MessageDispatcher, store: &SqliteStore) {
    let coord = store.get_friend("coord").await.expect("coord").expect("exists");
    let pro = store.get_friend("pro").await.expect("pro").expect("exists");
    dispatcher.agent_registry().inject_handle_for_test(
        "coord",
        Arc::new(StubAgent::with_prompt_rules(
            coord,
            &[
                (
                    "协调分工",
                    "拆成接口与测试两步。@攻坚 负责实现，我汇总进度。",
                ),
                (
                    "执行阶段",
                    "（主持）已分配 @攻坚，当前交付：登录模块重构方案 v1。",
                ),
                ("自荐", "（主持）我协调分工，自荐跟进整体进度。"),
            ],
            "coord-fallback",
        )),
    );
    dispatcher.agent_registry().inject_handle_for_test(
        "pro",
        Arc::new(StubAgent::with_prompt_rules(
            pro,
            &[(
                "自荐",
                "（攻坚）我擅长 hotfix 与重构，自荐负责实现与测试。",
            )],
            "pro-fallback",
        )),
    );
}

#[tokio::test]
async fn group_chitchat_send_user_message_stub_e2e() {
    let (_dir, store) = test_store().await;
    let conv_id = seed_single_agent_group(&store, false).await;

    let dispatcher = build_dispatcher(store.clone()).await;
    let friend = store.get_friend("pro").await.expect("get").expect("pro");
    dispatcher
        .agent_registry()
        .inject_handle_for_test("pro", Arc::new(StubAgent::new(friend, "e2e-stub")));

    let mut rx = dispatcher.subscribe();
    let _user_msg = dispatcher
        .send_user_message(&conv_id, "大家下午好")
        .await
        .expect("send");

    let events = wait_and_drain_events(&mut rx).await;
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::TurnIntentClassified { intent, .. } if intent == "chitchat"
        )),
        "应分类为 chitchat: {:?}",
        events
    );
    assert!(
        events.iter().any(|e| matches!(e, BusEvent::TurnStarted { .. })),
        "应有 TurnStarted"
    );
    assert!(
        events.iter().any(|e| matches!(e, BusEvent::TurnEnded { .. })),
        "应有 TurnEnded"
    );
    assert!(
        events
            .iter()
            .any(|e| matches!(e, BusEvent::JudgmentDecided { .. })),
        "应有 JudgmentDecided"
    );
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::MessageDone { message }
                if message.sender_kind == SenderKind::Friend
                    && message.content.contains("[占位回复]")
                    && message.status == MessageStatus::Done
        )),
        "StubAgent 应产出 Done 回复"
    );

    let history = store.recent_messages(&conv_id, 20).await.expect("history");
    assert!(
        history
            .iter()
            .any(|m| m.sender_id == "pro" && m.content.contains("[占位回复]")),
        "数据库应有 Agent 回复"
    );
}

#[tokio::test]
async fn group_task_intent_falls_through_to_stub_expert_when_task_flow_off() {
    let (_dir, store) = test_store().await;
    let conv_id = seed_single_agent_group(&store, false).await;

    let dispatcher = build_dispatcher(store.clone()).await;
    let friend = store.get_friend("pro").await.expect("get").expect("pro");
    dispatcher.agent_registry().inject_handle_for_test(
        "pro",
        Arc::new(StubAgent::with_fixed_reply(
            friend,
            "（攻坚）收到任务，我先梳理模块边界。",
        )),
    );

    let mut rx = dispatcher.subscribe();
    dispatcher
        .send_user_message(&conv_id, "请重构登录模块并补集成测试")
        .await
        .expect("send");

    let events = wait_and_drain_events(&mut rx).await;
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::TurnIntentClassified { intent, .. } if intent == "task"
        )),
        "应分类为 task"
    );
    assert!(
        !events
            .iter()
            .any(|e| matches!(e, BusEvent::TaskFlowPhase { .. })),
        "task_flow 关闭时不应进入任务流阶段"
    );
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::MessageDone { message }
                if message.sender_id == "pro"
                    && message.content.contains("梳理模块边界")
        )),
        "应走专家接话 Stub 回复"
    );
}

#[tokio::test]
async fn light_task_flow_appoint_by_mention_stub_e2e() {
    let (_dir, store) = test_store().await;
    let conv_id = seed_light_task_flow_group(store.clone(), "g-appoint").await;

    let dispatcher = build_dispatcher(store.clone()).await;
    let pro = store.get_friend("pro").await.expect("get").expect("pro");
    dispatcher.agent_registry().inject_handle_for_test(
        "pro",
        Arc::new(StubAgent::with_prompt_rules(
            pro,
            &[(
                "执行阶段",
                "（攻坚）登录模块重构已完成，测试用例已补全。",
            )],
            "pro-exec",
        )),
    );

    let mut rx = dispatcher.subscribe();
    dispatcher
        .send_user_message(&conv_id, "@攻坚 请重构登录模块并补集成测试")
        .await
        .expect("send");

    let events = wait_for_turn_end(&mut rx, 5000).await;
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::TurnIntentClassified { intent, .. } if intent == "task"
        ))
    );
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::TaskFlowPhase { phase, .. } if phase == "appoint"
        ))
    );
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::LeaderElected { friend_id, .. } if friend_id == "pro"
        ))
    );
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::TaskFlowPhase { phase, .. } if phase == "execute"
        ))
    );
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::MessageDone { message }
                if message.sender_id == "pro" && message.content.contains("测试用例已补全")
        ))
    );
    assert!(
        !events
            .iter()
            .any(|e| matches!(e, BusEvent::TaskFlowPhase { phase, .. } if phase == "peer_vote")),
        "light_task_flow 应跳过互投"
    );
}

#[tokio::test]
async fn light_task_flow_coordinator_and_nomination_stub_e2e() {
    let (_dir, store) = test_store().await;
    let conv_id = seed_light_task_flow_group(store.clone(), "g-coord").await;

    let dispatcher = build_dispatcher(store.clone()).await;
    inject_light_task_flow_stubs(&dispatcher, &store).await;

    let mut rx = dispatcher.subscribe();
    dispatcher
        .send_user_message(&conv_id, "请重构登录模块并补集成测试")
        .await
        .expect("send");

    let events = wait_for_turn_end(&mut rx, 8000).await;
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::TurnIntentClassified { intent, .. } if intent == "task"
        )),
        "events: {:?}",
        events
            .iter()
            .map(|e| format!("{e:?}"))
            .collect::<Vec<_>>()
    );
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::CoordinatorPlan { planner_id, assignee_ids, .. }
                if planner_id == "coord" && assignee_ids.contains(&"pro".into())
        )),
        "协调者应 @ 分工给攻坚"
    );
    assert!(
        events
            .iter()
            .any(|e| matches!(e, BusEvent::CampaignPitch { friend_id, .. } if friend_id == "pro")),
        "主动型攻坚应自荐"
    );
    assert!(
        !events.iter().any(|e| matches!(
            e,
            BusEvent::CampaignPitch { friend_id, .. } if friend_id == "passive"
        )),
        "被动成员不应自荐"
    );
    assert!(
        events.iter().any(|e| matches!(e, BusEvent::LeaderElected { .. })),
        "应产生 LeaderElected（选举失败时按竞选顺序兜底）"
    );
    assert!(
        events.iter().any(|e| matches!(e, BusEvent::TaskAssignmentsMerged { .. }))
    );
    assert!(
        events.iter().any(|e| matches!(
            e,
            BusEvent::TaskFlowPhase { phase, .. } if phase == "execute"
        ))
    );
    assert!(
        !events
            .iter()
            .any(|e| matches!(e, BusEvent::TaskFlowPhase { phase, .. } if phase == "peer_vote")),
        "light_task_flow 应跳过互投"
    );
}
