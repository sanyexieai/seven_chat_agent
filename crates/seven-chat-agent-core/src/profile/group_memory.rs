use chrono::Utc;
use futures::StreamExt;
use serde::{Deserialize, Serialize};

use std::collections::HashSet;

use crate::assistant_accumulation::truncate_chars;
use crate::domain::{AssistantGlobalSettings, GroupSettings, Message, MessageStatus, SenderKind};
use crate::memory_tier::{MEMORY_KIND_GROUP_PUBLIC, STATUS_ACTIVE, TIER_CURATED};
use crate::profile::{format_group_capability_excerpt, record_group_turn_capabilities, SCOPE_GROUP};
use std::sync::Arc;

use crate::provider::types::{ChatMessage, ProviderEvent};
use crate::provider::ProviderRegistry;
use crate::store::memory::{Memory, NewMemory};
use crate::store::SqliteStore;
use crate::Result;

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq)]
pub struct GroupPublicConsensus {
    #[serde(default)]
    pub facts: Vec<String>,
    #[serde(default)]
    pub assignments: Vec<GroupPublicAssignment>,
    #[serde(default)]
    pub open_questions: Vec<String>,
    #[serde(default)]
    pub failures: Vec<GroupPublicFailure>,
    #[serde(default)]
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq)]
pub struct GroupPublicAssignment {
    pub member: String,
    pub task: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq)]
pub struct GroupPublicFailure {
    pub member: String,
    pub reason: String,
}

pub const GROUP_PUBLIC_TITLE_LATEST: &str = "latest";

pub const BASELINE_CHAR_BUDGET: usize = 800;
pub const RELEVANT_CHAR_BUDGET: usize = 600;
pub const JUDGE_EXCERPT_CHAR_BUDGET: usize = 200;

pub fn group_public_expires_at(settings: &GroupSettings) -> Option<chrono::DateTime<Utc>> {
    let days = settings.orchestration.group_public_ttl_days;
    if days == 0 {
        None
    } else {
        Some(Utc::now() + chrono::Duration::days(days as i64))
    }
}

pub async fn fetch_group_public_baseline(
    store: &SqliteStore,
    assistant_owner_id: &str,
    group_id: &str,
) -> Result<String> {
    let rows = store
        .list_group_public_memories(assistant_owner_id, group_id, 8)
        .await?;
    Ok(format_group_public_baseline(&rows))
}

pub async fn fetch_group_public_judge_excerpt(
    store: &SqliteStore,
    assistant_owner_id: &str,
    group_id: &str,
) -> Result<Option<String>> {
    let latest = store
        .find_group_public_latest(assistant_owner_id, group_id)
        .await?;
    Ok(latest
        .as_ref()
        .map(format_group_public_judge_excerpt)
        .filter(|s| !s.trim().is_empty()))
}

pub fn format_group_public_judge_excerpt(mem: &Memory) -> String {
    if let Some(summary) = &mem.summary {
        if let Ok(c) = serde_json::from_str::<GroupPublicConsensus>(summary) {
            let excerpt = format_consensus_judge_excerpt(&c);
            if !excerpt.is_empty() {
                return excerpt;
            }
        }
    }
    truncate_chars(mem.content.trim(), JUDGE_EXCERPT_CHAR_BUDGET)
}

fn format_consensus_judge_excerpt(c: &GroupPublicConsensus) -> String {
    let mut bullets: Vec<String> = Vec::new();
    for f in &c.failures {
        bullets.push(format!(
            "{}失败：{}",
            f.member,
            truncate_chars(f.reason.trim(), 50)
        ));
    }
    for a in &c.assignments {
        if bullets.len() >= 3 {
            break;
        }
        bullets.push(format!(
            "{}：{}",
            a.member,
            truncate_chars(a.task.trim(), 50)
        ));
    }
    for fact in &c.facts {
        if bullets.len() >= 3 {
            break;
        }
        bullets.push(truncate_chars(fact.trim(), 60));
    }
    if bullets.is_empty() {
        return String::new();
    }
    let body = bullets
        .into_iter()
        .take(3)
        .map(|b| format!("- {b}"))
        .collect::<Vec<_>>()
        .join("\n");
    truncate_chars(&body, JUDGE_EXCERPT_CHAR_BUDGET)
}

pub async fn fetch_group_public_relevant(
    store: &SqliteStore,
    assistant_owner_id: &str,
    group_id: &str,
    query: &str,
    limit: i64,
) -> Result<String> {
    let limit = limit.clamp(1, 16);
    let rows = store
        .search_group_public_memories(assistant_owner_id, group_id, query, limit)
        .await?;
    Ok(format_group_public_relevant(&rows))
}

/// FTS + 可选向量合并（`Arc` 避免 dispatch 路径自引用 future 溢出 E0275）。
pub async fn fetch_group_public_relevant_with_embedding(
    store: &SqliteStore,
    providers: Arc<ProviderRegistry>,
    settings: AssistantGlobalSettings,
    assistant_owner_id: &str,
    group_id: &str,
    query: &str,
    limit: i64,
) -> Result<String> {
    let limit = limit.clamp(1, 16);
    let mut rows = store
        .search_group_public_memories(assistant_owner_id, group_id, query, limit)
        .await?;
    let mut seen: HashSet<String> = rows.iter().map(|m| m.id.clone()).collect();
    if settings.embedding_enabled {
        for m in store
            .search_group_public_memories_vector(
                assistant_owner_id,
                group_id,
                query,
                limit,
                providers.as_ref(),
                &settings,
                assistant_owner_id,
            )
            .await
            .unwrap_or_default()
        {
            if seen.insert(m.id.clone()) {
                rows.push(m);
            }
        }
    }
    rows.truncate(limit as usize);
    Ok(format_group_public_relevant(&rows))
}

pub fn append_group_public_baseline_prompt(s: &mut String, baseline: Option<&str>) {
    if let Some(block) = baseline.filter(|b| !b.trim().is_empty()) {
        s.push_str("\n\n");
        s.push_str(block);
    }
}

pub fn format_group_public_baseline(rows: &[Memory]) -> String {
    if rows.is_empty() {
        return String::new();
    }
    let mut parts: Vec<String> = Vec::new();
    let mut used = 0usize;

    if let Some(latest) = rows
        .iter()
        .find(|m| m.title.as_deref() == Some(GROUP_PUBLIC_TITLE_LATEST))
    {
        let text = truncate_chars(latest.content.trim(), BASELINE_CHAR_BUDGET);
        used += text.chars().count();
        parts.push(format!("【共识】{text}"));
    }

    for m in rows
        .iter()
        .filter(|m| m.pinned && m.title.as_deref() != Some(GROUP_PUBLIC_TITLE_LATEST))
    {
        if used >= BASELINE_CHAR_BUDGET {
            break;
        }
        let remain = BASELINE_CHAR_BUDGET.saturating_sub(used);
        let text = truncate_chars(m.content.trim(), remain.min(400));
        used += text.chars().count();
        parts.push(format!("【置顶】{text}"));
    }

    if parts.is_empty() {
        let text = truncate_chars(rows[0].content.trim(), BASELINE_CHAR_BUDGET);
        parts.push(format!("【共识】{text}"));
    }

    format!("[本群共识 · 只读]\n{}", parts.join("\n"))
}

pub fn format_group_public_relevant(rows: &[Memory]) -> String {
    if rows.is_empty() {
        return String::new();
    }
    let mut lines: Vec<String> = Vec::new();
    let mut used = 0usize;
    for m in rows {
        if used >= RELEVANT_CHAR_BUDGET {
            break;
        }
        let remain = RELEVANT_CHAR_BUDGET.saturating_sub(used);
        let body = m
            .summary
            .as_deref()
            .filter(|s| !s.trim().is_empty())
            .unwrap_or(&m.content);
        let line = truncate_chars(body.trim(), remain.min(300));
        used += line.chars().count();
        lines.push(format!("- {line}"));
    }
    format!("[与本话题相关的群记忆]\n{}", lines.join("\n"))
}

pub async fn upsert_group_public_latest(
    store: &SqliteStore,
    assistant_owner_id: &str,
    group_id: &str,
    content: &str,
    summary_json: Option<&str>,
    settings: Option<&GroupSettings>,
) -> Result<Memory> {
    let expires_at = settings.and_then(group_public_expires_at);
    let content = content.trim();
    if content.is_empty() {
        return Err(crate::Error::bad_request("group_public content empty"));
    }
    let summary_owned = summary_json.map(String::from);
    if let Some(existing) = store
        .find_group_public_latest(assistant_owner_id, group_id)
        .await?
    {
        let updated = store
            .update_memory(
                &existing.id,
                None,
                Some(content),
                Some(0.85),
                None,
                None,
                None,
                None,
                Some(2),
                None,
                Some(Some(GROUP_PUBLIC_TITLE_LATEST)),
                Some(summary_owned.as_deref()),
                false,
            )
            .await?;
        store
            .set_memory_expires_at(&existing.id, expires_at)
            .await?;
        return Ok(updated);
    }
    store
        .insert_memory(NewMemory {
            owner_friend_id: assistant_owner_id.to_string(),
            kind: MEMORY_KIND_GROUP_PUBLIC.to_string(),
            content: content.to_string(),
            source_message_id: None,
            weight: 0.85,
            pinned: false,
            tier: TIER_CURATED.to_string(),
            scope: SCOPE_GROUP.to_string(),
            scope_ref: Some(group_id.to_string()),
            importance: 2,
            status: STATUS_ACTIVE.to_string(),
            title: Some(GROUP_PUBLIC_TITLE_LATEST.to_string()),
            summary: summary_owned,
            expires_at,
            workspace_id: None,
        })
        .await
}

/// 从协调者分工正文解析 `@成员` 对应任务片段。
pub fn parse_assignments_from_coordinator_plan(
    plan_content: &str,
    assignees: &[(String, String)],
) -> Vec<GroupPublicAssignment> {
    if assignees.is_empty() {
        return vec![];
    }
    let content = plan_content.trim();
    if content.is_empty() {
        return assignees
            .iter()
            .map(|(_, name)| GroupPublicAssignment {
                member: name.clone(),
                task: "协调分工".into(),
            })
            .collect();
    }
    let mut positions: Vec<(String, usize, usize)> = Vec::new();
    for (_, name) in assignees {
        let needle = format!("@{name}");
        if let Some(pos) = content.find(&needle) {
            positions.push((name.clone(), pos, pos + needle.len()));
        }
    }
    positions.sort_by_key(|(_, pos, _)| *pos);

    let mut out = Vec::new();
    for (i, (name, _, after)) in positions.iter().enumerate() {
        let rest = &content[*after..];
        let end = if i + 1 < positions.len() {
            let next_start = positions[i + 1].1;
            next_start.saturating_sub(*after)
        } else {
            rest.len()
        };
        let slice = rest[..end.min(rest.len())].trim();
        let trimmed = slice
            .trim_start_matches(['：', ':', '，', ',', '、', ' '])
            .trim();
        let task = if trimmed.is_empty() {
            truncate_chars(content, 120)
        } else {
            truncate_chars(trimmed, 120)
        };
        out.push(GroupPublicAssignment {
            member: name.clone(),
            task,
        });
    }
    for (_, name) in assignees {
        if !out.iter().any(|a| a.member == *name) {
            out.push(GroupPublicAssignment {
                member: name.clone(),
                task: truncate_chars(content, 120),
            });
        }
    }
    dedupe_assignments(out)
}

/// 任务流协调者分工后即时合并 assignments 到群共识 latest。
pub async fn merge_coordinator_plan_into_group_public(
    store: &SqliteStore,
    settings: &GroupSettings,
    assistant_owner_id: &str,
    group_id: &str,
    plan_content: &str,
    assignees: &[(String, String)],
) -> Result<bool> {
    if !settings.orchestration.group_memory_enabled {
        return Ok(false);
    }
    let new_assignments = parse_assignments_from_coordinator_plan(plan_content, assignees);
    if new_assignments.is_empty() {
        return Ok(false);
    }

    let mut consensus: GroupPublicConsensus = store
        .find_group_public_latest(assistant_owner_id, group_id)
        .await?
        .and_then(|m| {
            m.summary
                .as_ref()
                .and_then(|s| serde_json::from_str(s).ok())
        })
        .unwrap_or_default();

    consensus.assignments.extend(new_assignments);
    consensus.assignments = dedupe_assignments(consensus.assignments);
    let plan_fact = truncate_chars(plan_content.trim(), 160);
    if !plan_fact.is_empty() {
        consensus
            .facts
            .push(format!("协调分工：{plan_fact}"));
        consensus.facts = dedupe_strings(consensus.facts);
        consensus.facts.truncate(8);
    }
    consensus.updated_at = Some(Utc::now().to_rfc3339());

    let markdown = consensus_to_markdown(&consensus);
    if markdown.trim().is_empty() {
        return Ok(false);
    }
    let summary = serde_json::to_string(&consensus).ok();
    upsert_group_public_latest(
        store,
        assistant_owner_id,
        group_id,
        &markdown,
        summary.as_deref(),
        Some(settings),
    )
    .await?;
    tracing::info!(
        group_id = %group_id,
        assignments = consensus.assignments.len(),
        "group_public merged coordinator plan"
    );
    Ok(true)
}

pub fn consensus_to_markdown(c: &GroupPublicConsensus) -> String {
    let mut parts: Vec<String> = Vec::new();
    if !c.facts.is_empty() {
        let mut block = String::from("## 已确认事实\n");
        for f in &c.facts {
            block.push_str(&format!("- {f}\n"));
        }
        parts.push(block.trim_end().to_string());
    }
    if !c.assignments.is_empty() {
        let mut block = String::from("## 分工\n");
        for a in &c.assignments {
            block.push_str(&format!("- {}：{}\n", a.member, a.task));
        }
        parts.push(block.trim_end().to_string());
    }
    if !c.open_questions.is_empty() {
        let mut block = String::from("## 未决问题\n");
        for q in &c.open_questions {
            block.push_str(&format!("- {q}\n"));
        }
        parts.push(block.trim_end().to_string());
    }
    if !c.failures.is_empty() {
        let mut block = String::from("## 发言失败记录\n");
        for f in &c.failures {
            block.push_str(&format!("- {}：{}\n", f.member, f.reason));
        }
        parts.push(block.trim_end().to_string());
    }
    parts.join("\n\n")
}

impl GroupPublicConsensus {
    pub fn is_effectively_empty(&self) -> bool {
        self.facts.is_empty()
            && self.assignments.is_empty()
            && self.open_questions.is_empty()
            && self.failures.is_empty()
    }
}

pub fn summarize_turn_dialogue(history: &[Message], turn_id: &str) -> String {
    let lines: Vec<String> = history
        .iter()
        .filter(|m| m.turn_id == turn_id && m.sender_kind != SenderKind::System)
        .map(|m| {
            let who = match m.sender_kind {
                SenderKind::User => "用户".to_string(),
                SenderKind::Friend => m.sender_name.clone(),
                SenderKind::System => "系统".into(),
            };
            format!(
                "- {who}：{}",
                crate::message_context::format_message_content_for_context(m)
            )
        })
        .collect();
    if lines.is_empty() {
        "（本回合暂无消息）".into()
    } else {
        lines.join("\n")
    }
}

fn collect_turn_failures(history: &[Message], turn_id: &str) -> Vec<GroupPublicFailure> {
    history
        .iter()
        .filter(|m| {
            m.turn_id == turn_id
                && m.status == MessageStatus::Failed
                && m.sender_kind == SenderKind::Friend
        })
        .map(|m| GroupPublicFailure {
            member: m.sender_name.clone(),
            reason: truncate_chars(
                &crate::message_context::format_message_content_for_context(m),
                200,
            ),
        })
        .collect()
}

fn user_task_in_turn(history: &[Message], turn_id: &str) -> String {
    history
        .iter()
        .find(|m| m.turn_id == turn_id && m.sender_kind == SenderKind::User)
        .map(|m| m.content.trim().to_string())
        .unwrap_or_default()
}

fn parse_assignments_from_mentions(history: &[Message], turn_id: &str) -> Vec<GroupPublicAssignment> {
    let mut out = Vec::new();
    for m in history
        .iter()
        .filter(|m| m.turn_id == turn_id && m.sender_kind == SenderKind::Friend)
    {
        if m.mentions.is_empty() {
            continue;
        }
        let excerpt = truncate_chars(m.content.trim(), 120);
        if excerpt.is_empty() {
            continue;
        }
        for name in &m.mentions {
            out.push(GroupPublicAssignment {
                member: name.clone(),
                task: excerpt.clone(),
            });
        }
    }
    out
}

fn dedupe_strings(items: Vec<String>) -> Vec<String> {
    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for s in items {
        let key = s.trim().to_string();
        if key.is_empty() || !seen.insert(key.clone()) {
            continue;
        }
        out.push(key);
    }
    out
}

fn dedupe_assignments(items: Vec<GroupPublicAssignment>) -> Vec<GroupPublicAssignment> {
    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for a in items {
        let key = format!("{}|{}", a.member, a.task);
        if seen.insert(key) {
            out.push(a);
        }
    }
    out
}

pub fn heuristic_curate_group_public(
    history: &[Message],
    turn_id: &str,
    raw_capability: &str,
    old_latest: Option<&str>,
    extra_assignments: &[GroupPublicAssignment],
) -> GroupPublicConsensus {
    let user_task = user_task_in_turn(history, turn_id);
    let turn_dialogue = summarize_turn_dialogue(history, turn_id);
    let failures = collect_turn_failures(history, turn_id);

    let mut facts: Vec<String> = Vec::new();
    if let Some(old) = old_latest.filter(|s| !s.trim().is_empty()) {
        for line in old.lines() {
            let t = line.trim();
            if t.starts_with("- ") {
                facts.push(t.trim_start_matches("- ").to_string());
            }
        }
    }
    if !user_task.trim().is_empty() {
        facts.push(format!("用户本轮：{}", truncate_chars(user_task.trim(), 160)));
    }
    for line in turn_dialogue.lines() {
        let t = line.trim();
        if t.starts_with("- ") && !t.contains("用户") {
            facts.push(truncate_chars(t.trim_start_matches("- "), 160));
        }
    }
    if !raw_capability.trim().is_empty() {
        facts.push(truncate_chars(raw_capability.trim(), 200));
    }
    facts = dedupe_strings(facts);
    facts.truncate(8);

    let mut assignments = extra_assignments.to_vec();
    assignments.extend(parse_assignments_from_mentions(history, turn_id));
    assignments = dedupe_assignments(assignments);

    let mut open_questions: Vec<String> = Vec::new();
    if user_task.contains('?') || user_task.contains('？') {
        open_questions.push(truncate_chars(user_task.trim(), 120));
    }

    GroupPublicConsensus {
        facts,
        assignments,
        open_questions,
        failures,
        updated_at: Some(Utc::now().to_rfc3339()),
    }
}

async fn curate_group_public_with_llm(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    user_task: &str,
    turn_dialogue: &str,
    raw_capability: &str,
    old_latest: Option<&str>,
    failures: &[GroupPublicFailure],
) -> Result<GroupPublicConsensus> {
    let failures_json = serde_json::to_string(failures).unwrap_or_else(|_| "[]".into());
    let old_block = old_latest.unwrap_or("（无）");
    let user_prompt = format!(
        "你是群聊共识整理器（Curator）。根据输入更新本群共识 JSON，禁止编造未出现的事实。\n\n\
         【用户任务】\n{user_task}\n\n\
         【本回合群聊】\n{turn_dialogue}\n\n\
         【成员表现 raw】\n{raw_capability}\n\n\
         【旧共识】\n{old_block}\n\n\
         【本回合失败】\n{failures_json}\n\n\
         输出 JSON：{{\"facts\":[\"…\"],\"assignments\":[{{\"member\":\"名\",\"task\":\"…\"}}],\
         \"open_questions\":[\"…\"],\"failures\":[{{\"member\":\"名\",\"reason\":\"…\"}}],\
         \"updated_at\":\"ISO8601\"}}\n\
         failures 仅记录确实发送失败的成员；不要把失败当作已成功发言。"
    );

    let (provider_id, model) = resolve_curator_target()?;
    let provider = providers
        .get(&provider_id)
        .ok_or_else(|| crate::Error::Config(format!("curator provider not found: {provider_id}")))?;
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
                ChatMessage::system("只输出一个 JSON 对象，不要 markdown。"),
                ChatMessage::user(user_prompt),
            ],
            temperature: Some(0.2),
            top_p: None,
            max_tokens: Some(1024),
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

    let json = crate::llm_json::extract_json_object(&raw).unwrap_or(raw);
    let mut consensus: GroupPublicConsensus = serde_json::from_str(&json)
        .map_err(|e| crate::Error::Config(format!("curator JSON parse: {e}")))?;
    if consensus.updated_at.is_none() {
        consensus.updated_at = Some(Utc::now().to_rfc3339());
    }
    Ok(consensus)
}

fn resolve_curator_target() -> Result<(String, String)> {
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
        "未配置 Curator Provider（ASSISTANT 或 JUDGE 环境变量）".into(),
    ))
}

/// 整理本回合群共识并 UPSERT `group_public` latest。
pub async fn curate_group_public_from_turn(
    store: &SqliteStore,
    providers: Option<&ProviderRegistry>,
    settings: &GroupSettings,
    assistant_owner_id: &str,
    group_id: &str,
    turn_id: &str,
    history: &[Message],
    extra_assignments: &[GroupPublicAssignment],
) -> Result<bool> {
    let user_task = user_task_in_turn(history, turn_id);
    let turn_dialogue = summarize_turn_dialogue(history, turn_id);
    let failures = collect_turn_failures(history, turn_id);
    let raw_capability = format_group_capability_excerpt(store, assistant_owner_id, group_id, 5)
        .await
        .unwrap_or_default();
    let old_latest = store
        .find_group_public_latest(assistant_owner_id, group_id)
        .await?
        .map(|m| m.content);

    let consensus = if let Some(providers) = providers {
        match curate_group_public_with_llm(
            store,
            providers,
            &user_task,
            &turn_dialogue,
            &raw_capability,
            old_latest.as_deref(),
            &failures,
        )
        .await
        {
            Ok(c) => c,
            Err(e) => {
                tracing::warn!(err = %e, turn_id = %turn_id, "group_public curator LLM failed, heuristic fallback");
                heuristic_curate_group_public(
                    history,
                    turn_id,
                    &raw_capability,
                    old_latest.as_deref(),
                    extra_assignments,
                )
            }
        }
    } else {
        heuristic_curate_group_public(
            history,
            turn_id,
            &raw_capability,
            old_latest.as_deref(),
            extra_assignments,
        )
    };

    if consensus.is_effectively_empty() {
        return Ok(false);
    }

    let markdown = consensus_to_markdown(&consensus);
    let summary = serde_json::to_string(&consensus).ok();
    upsert_group_public_latest(
        store,
        assistant_owner_id,
        group_id,
        &markdown,
        summary.as_deref(),
        Some(settings),
    )
    .await?;
    tracing::info!(
        turn_id = %turn_id,
        group_id = %group_id,
        facts = consensus.facts.len(),
        failures = consensus.failures.len(),
        "group_public latest updated"
    );
    Ok(true)
}

/// 同回合串行接话：第二名及以后成员接话前，启发式刷新共识（无 LLM）。
pub async fn refresh_group_public_mid_turn(
    store: &SqliteStore,
    settings: &GroupSettings,
    assistant_owner_id: &str,
    group_id: &str,
    conversation_id: &str,
    turn_id: &str,
) -> bool {
    if !settings.orchestration.group_memory_enabled {
        return false;
    }
    let history = store
        .recent_messages(conversation_id, 60)
        .await
        .unwrap_or_default();
    curate_group_public_from_turn(
        store,
        None,
        settings,
        assistant_owner_id,
        group_id,
        turn_id,
        &history,
        &[],
    )
    .await
    .unwrap_or(false)
}

/// 用户回合末：写 raw capability + 整理 latest 共识。
pub async fn finalize_group_turn_memory(
    store: &SqliteStore,
    providers: Option<&ProviderRegistry>,
    settings: &GroupSettings,
    conversation_id: &str,
    group_id: &str,
    turn_id: &str,
    extra_assignments: &[GroupPublicAssignment],
) -> bool {
    if !settings.orchestration.group_memory_enabled {
        return false;
    }
    let Ok(Some(assistant_id)) = store.builtin_assistant_id().await else {
        return false;
    };
    if let Ok(n) = store.archive_expired_memories(&assistant_id).await {
        if n > 0 {
            tracing::debug!(archived = n, "group_public expired memories archived");
        }
    }
    let history = store
        .recent_messages(conversation_id, 60)
        .await
        .unwrap_or_default();
    if let Err(e) = record_group_turn_capabilities(
        store,
        &assistant_id,
        group_id,
        turn_id,
        &history,
    )
    .await
    {
        tracing::debug!(err = %e, "group_capability memory skipped");
    } else if let Ok(n) =
        crate::profile::archive_excess_group_capability_raw(store, &assistant_id, group_id).await
    {
        if n > 0 {
            tracing::debug!(archived = n, group_id = %group_id, "group_capability raw archived");
        }
    }
    match curate_group_public_from_turn(
        store,
        providers,
        settings,
        &assistant_id,
        group_id,
        turn_id,
        &history,
        extra_assignments,
    )
    .await
    {
        Ok(updated) => updated,
        Err(e) => {
            tracing::debug!(err = %e, "group_public curator skipped");
            false
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::{Message, MessageStatus, SenderKind};
    use crate::memory_tier::{MEMORY_KIND_GROUP_PUBLIC, STATUS_ACTIVE, TIER_CURATED};
    use crate::profile::SCOPE_GROUP;
    use crate::store::memory::NewMemory;
    use chrono::Utc;

    fn mem(content: &str, title: Option<&str>, pinned: bool) -> Memory {
        Memory {
            id: "m1".into(),
            owner_friend_id: "a".into(),
            kind: MEMORY_KIND_GROUP_PUBLIC.to_string(),
            content: content.into(),
            source_message_id: None,
            weight: 1.0,
            pinned,
            last_used_at: None,
            decay_score: 1.0,
            created_at: Utc::now(),
            tier: TIER_CURATED.to_string(),
            scope: SCOPE_GROUP.to_string(),
            scope_ref: Some("g1".into()),
            importance: 1,
            status: STATUS_ACTIVE.to_string(),
            title: title.map(String::from),
            summary: None,
            tenant_id: "t".into(),
            expires_at: None,
            workspace_id: None,
        }
    }

    #[test]
    fn format_baseline_prefers_latest_title() {
        let rows = vec![
            mem("旧摘要", Some("old"), false),
            mem("当前共识：分工已定", Some(GROUP_PUBLIC_TITLE_LATEST), false),
        ];
        let out = format_group_public_baseline(&rows);
        assert!(out.contains("[本群共识 · 只读]"));
        assert!(out.contains("当前共识"));
        assert!(!out.contains("旧摘要"));
    }

    #[test]
    fn format_relevant_empty_returns_empty() {
        assert!(format_group_public_relevant(&[]).is_empty());
    }

    #[test]
    fn judge_excerpt_prioritizes_failures() {
        let c = GroupPublicConsensus {
            facts: vec!["事实一".into()],
            failures: vec![GroupPublicFailure {
                member: "甲".into(),
                reason: "发送失败".into(),
            }],
            ..Default::default()
        };
        let excerpt = format_consensus_judge_excerpt(&c);
        assert!(excerpt.contains("甲"));
        assert!(excerpt.contains("失败"));
    }

    #[tokio::test]
    async fn list_and_search_group_public_roundtrip() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("group_mem.db");
        let url = format!("sqlite://{}?mode=rwc", path.display());
        let store = SqliteStore::connect(&url).await.expect("connect");
        store.migrate().await.expect("migrate");
        store.ensure_tenant().await.expect("tenant");

        let assistant = "asst1";
        let group_id = "grp1";
        store
            .upsert_friend(crate::store::friend::UpsertFriend {
                id: Some(assistant.into()),
                name: "助理".into(),
                avatar: None,
                system_prompt: String::new(),
                personality: None,
                focus_tags: vec![],
                backend_kind: crate::domain::BackendKind::Api,
                backend_config: serde_json::json!({}),
                judge_provider_ref: None,
                enabled: true,
            })
            .await
            .expect("friend");
        store
            .insert_memory(NewMemory {
                owner_friend_id: assistant.into(),
                kind: MEMORY_KIND_GROUP_PUBLIC.to_string(),
                content: "本群约定：后端由 Alice 负责，前端由 Bob 负责。".into(),
                source_message_id: None,
                weight: 0.8,
                pinned: false,
                tier: TIER_CURATED.to_string(),
                scope: SCOPE_GROUP.to_string(),
                scope_ref: Some(group_id.into()),
                importance: 2,
                status: STATUS_ACTIVE.to_string(),
                title: Some(GROUP_PUBLIC_TITLE_LATEST.into()),
                summary: Some("分工：Alice 后端，Bob 前端".into()),
                expires_at: None,
                workspace_id: None,
            })
            .await
            .expect("insert");

        let listed = store
            .list_group_public_memories(assistant, group_id, 5)
            .await
            .expect("list");
        assert_eq!(listed.len(), 1);

        let baseline = format_group_public_baseline(&listed);
        assert!(baseline.contains("Alice"));

        let hits = store
            .search_group_public_memories(assistant, group_id, "Alice 后端", 3)
            .await
            .expect("search");
        assert!(!hits.is_empty());
        let relevant = format_group_public_relevant(&hits);
        assert!(relevant.contains("[与本话题相关的群记忆]"));
    }

    #[tokio::test]
    async fn upsert_group_public_latest_updates_single_row() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("upsert.db");
        let url = format!("sqlite://{}?mode=rwc", path.display());
        let store = SqliteStore::connect(&url).await.expect("connect");
        store.migrate().await.expect("migrate");
        store.ensure_tenant().await.expect("tenant");
        store
            .upsert_friend(crate::store::friend::UpsertFriend {
                id: Some("asst".into()),
                name: "助理".into(),
                avatar: None,
                system_prompt: String::new(),
                personality: None,
                focus_tags: vec![],
                backend_kind: crate::domain::BackendKind::Api,
                backend_config: serde_json::json!({}),
                judge_provider_ref: None,
                enabled: true,
            })
            .await
            .expect("friend");

        let first = upsert_group_public_latest(
            &store,
            "asst",
            "g1",
            "## 已确认事实\n- 初版共识",
            None,
            None,
        )
        .await
        .expect("insert");
        let second = upsert_group_public_latest(
            &store,
            "asst",
            "g1",
            "## 已确认事实\n- 更新后共识",
            None,
            None,
        )
        .await
        .expect("update");
        assert_eq!(first.id, second.id);
        let listed = store
            .list_group_public_memories("asst", "g1", 5)
            .await
            .expect("list");
        assert_eq!(listed.len(), 1);
        assert!(listed[0].content.contains("更新后"));
    }

    #[tokio::test]
    async fn heuristic_includes_peer_reply_for_serial_refresh() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("mid_turn.db");
        let url = format!("sqlite://{}?mode=rwc", path.display());
        let store = SqliteStore::connect(&url).await.expect("connect");
        store.migrate().await.expect("migrate");
        store.ensure_tenant().await.expect("tenant");
        store
            .upsert_friend(crate::store::friend::UpsertFriend {
                id: Some("asst".into()),
                name: "助理".into(),
                avatar: None,
                system_prompt: String::new(),
                personality: None,
                focus_tags: vec![],
                backend_kind: crate::domain::BackendKind::Api,
                backend_config: serde_json::json!({}),
                judge_provider_ref: None,
                enabled: true,
            })
            .await
            .expect("friend");

        let turn_id = "turn-serial-1";
        let conv_id = "conv1";
        let group_id = "g1";
        let history = vec![Message {
            id: "u1".into(),
            conversation_id: conv_id.into(),
            turn_id: turn_id.into(),
            parent_id: None,
            sender_kind: SenderKind::User,
            sender_id: "user".into(),
            sender_name: "用户".into(),
            on_behalf_of_user: false,
            content: "请分工".into(),
            content_blocks: None,
            mentions: vec![],
            status: MessageStatus::Done,
            seen_by: vec![],
            model_used: None,
            tokens_in: None,
            tokens_out: None,
            workspace_id: None,
            attachments: vec![],
            created_at: Utc::now(),
        }];

        let mut history2 = history;
        history2.push(Message {
            id: "f1".into(),
            conversation_id: conv_id.into(),
            turn_id: turn_id.into(),
            parent_id: Some("u1".into()),
            sender_kind: SenderKind::Friend,
            sender_id: "a".into(),
            sender_name: "甲".into(),
            on_behalf_of_user: false,
            content: "我负责后端 API 设计与实现".into(),
            content_blocks: None,
            mentions: vec![],
            status: MessageStatus::Done,
            seen_by: vec![],
            model_used: None,
            tokens_in: None,
            tokens_out: None,
            workspace_id: None,
            attachments: vec![],
            created_at: Utc::now(),
        });
        // simulate mid-turn refresh with peer reply in history
        let consensus = heuristic_curate_group_public(&history2, turn_id, "", None, &[]);
        upsert_group_public_latest(
            &store,
            "asst",
            group_id,
            &consensus_to_markdown(&consensus),
            None,
            None,
        )
        .await
        .expect("upsert");
        let latest = store
            .find_group_public_latest("asst", group_id)
            .await
            .expect("find")
            .expect("latest");
        assert!(latest.content.contains("后端"));
    }

    #[tokio::test]
    async fn heuristic_curate_captures_failures() {
        let turn_id = "turn-abc12345";
        let history = vec![
            Message {
                id: "u1".into(),
                conversation_id: "c".into(),
                turn_id: turn_id.into(),
                parent_id: None,
                sender_kind: SenderKind::User,
                sender_id: "user".into(),
                sender_name: "用户".into(),
                on_behalf_of_user: false,
                content: "请分工".into(),
                content_blocks: None,
                mentions: vec![],
                status: MessageStatus::Done,
                seen_by: vec![],
                model_used: None,
                tokens_in: None,
                tokens_out: None,
                workspace_id: None,
                attachments: vec![],
                created_at: Utc::now(),
            },
            Message {
                id: "f1".into(),
                conversation_id: "c".into(),
                turn_id: turn_id.into(),
                parent_id: Some("u1".into()),
                sender_kind: SenderKind::Friend,
                sender_id: "a".into(),
                sender_name: "甲".into(),
                on_behalf_of_user: false,
                content: String::new(),
                content_blocks: None,
                mentions: vec![],
                status: MessageStatus::Failed,
                seen_by: vec![],
                model_used: None,
                tokens_in: None,
                tokens_out: None,
                workspace_id: None,
                attachments: vec![],
                created_at: Utc::now(),
            },
        ];
        let consensus = heuristic_curate_group_public(&history, turn_id, "", None, &[]);
        assert_eq!(consensus.failures.len(), 1);
        assert_eq!(consensus.failures[0].member, "甲");
        let md = consensus_to_markdown(&consensus);
        assert!(md.contains("发言失败"));
    }

    #[test]
    fn parse_coordinator_plan_assignments_splits_tasks() {
        let assignees = vec![
            ("a".into(), "Alice".into()),
            ("b".into(), "Bob".into()),
        ];
        let plan = "请 @Alice 写接口，@Bob 做测试";
        let got = parse_assignments_from_coordinator_plan(plan, &assignees);
        assert_eq!(got.len(), 2);
        assert_eq!(got[0].member, "Alice");
        assert!(got[0].task.contains("写接口"));
        assert_eq!(got[1].member, "Bob");
        assert!(got[1].task.contains("测试"));
    }

    #[tokio::test]
    async fn expired_group_public_not_listed_after_archive() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("expire.db");
        let url = format!("sqlite://{}?mode=rwc", path.display());
        let store = SqliteStore::connect(&url).await.expect("connect");
        store.migrate().await.expect("migrate");
        store.ensure_tenant().await.expect("tenant");
        store
            .upsert_friend(crate::store::friend::UpsertFriend {
                id: Some("asst".into()),
                name: "助理".into(),
                avatar: None,
                system_prompt: String::new(),
                personality: None,
                focus_tags: vec![],
                backend_kind: crate::domain::BackendKind::Api,
                backend_config: serde_json::json!({}),
                judge_provider_ref: None,
                enabled: true,
            })
            .await
            .expect("friend");

        let past = Utc::now() - chrono::Duration::days(1);
        store
            .insert_memory(NewMemory {
                owner_friend_id: "asst".into(),
                kind: MEMORY_KIND_GROUP_PUBLIC.to_string(),
                content: "过期共识".into(),
                source_message_id: None,
                weight: 0.8,
                pinned: false,
                tier: TIER_CURATED.to_string(),
                scope: SCOPE_GROUP.to_string(),
                scope_ref: Some("g1".into()),
                importance: 2,
                status: STATUS_ACTIVE.to_string(),
                title: Some(GROUP_PUBLIC_TITLE_LATEST.into()),
                summary: None,
                expires_at: Some(past),
                workspace_id: None,
            })
            .await
            .expect("insert");

        let listed = store
            .list_group_public_memories("asst", "g1", 5)
            .await
            .expect("list");
        assert!(listed.is_empty());

        let archived = store.archive_expired_memories("asst").await.expect("archive");
        assert_eq!(archived, 1);
    }

    #[tokio::test]
    async fn merge_coordinator_plan_updates_latest() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("coord.db");
        let url = format!("sqlite://{}?mode=rwc", path.display());
        let store = SqliteStore::connect(&url).await.expect("connect");
        store.migrate().await.expect("migrate");
        store.ensure_tenant().await.expect("tenant");
        store
            .upsert_friend(crate::store::friend::UpsertFriend {
                id: Some("asst".into()),
                name: "助理".into(),
                avatar: None,
                system_prompt: String::new(),
                personality: None,
                focus_tags: vec![],
                backend_kind: crate::domain::BackendKind::Api,
                backend_config: serde_json::json!({}),
                judge_provider_ref: None,
                enabled: true,
            })
            .await
            .expect("friend");

        let settings = crate::domain::GroupSettings::default();
        let assignees = vec![("a".into(), "Alice".into())];
        let updated = merge_coordinator_plan_into_group_public(
            &store,
            &settings,
            "asst",
            "g1",
            "请 @Alice 负责 API 设计",
            &assignees,
        )
        .await
        .expect("merge");
        assert!(updated);
        let latest = store
            .find_group_public_latest("asst", "g1")
            .await
            .expect("find")
            .expect("latest");
        assert!(latest.content.contains("Alice"));
        assert!(latest.content.contains("API"));
    }
}
