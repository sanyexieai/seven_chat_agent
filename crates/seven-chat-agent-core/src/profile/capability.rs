use crate::assistant_accumulation::truncate_chars;
use crate::domain::{Message, SenderKind};
use crate::store::memory::{ListMemoryFilter, NewMemory};
use crate::store::SqliteStore;
use crate::Result;

pub const MEMORY_KIND_GROUP_CAPABILITY: &str = "group_capability";
pub const SCOPE_GROUP: &str = "group";

/// 每群保留的 raw `group_capability` 条数，超出部分归档。
pub const MAX_GROUP_CAPABILITY_RAW_PER_GROUP: i64 = 48;

/// 回合结束后记录各成员在本群的表现摘要（供协调者 recall）。
pub async fn record_group_turn_capabilities(
    store: &SqliteStore,
    assistant_owner_id: &str,
    group_id: &str,
    turn_id: &str,
    messages: &[Message],
) -> Result<()> {
    let mut by_friend: std::collections::HashMap<String, Vec<String>> =
        std::collections::HashMap::new();
    for m in messages {
        if m.turn_id != turn_id || m.sender_kind != SenderKind::Friend {
            continue;
        }
        let excerpt = truncate_chars(m.content.trim(), 120);
        if excerpt.is_empty() {
            continue;
        }
        by_friend
            .entry(m.sender_id.clone())
            .or_default()
            .push(format!("[{}] {}", m.sender_name, excerpt));
    }
    for (friend_id, lines) in by_friend {
        if lines.is_empty() {
            continue;
        }
        let content = format!(
            "群成员表现（turn={}）\n{}",
            &turn_id[..turn_id.len().min(8)],
            lines.join("\n")
        );
        store
            .insert_memory(NewMemory {
                owner_friend_id: assistant_owner_id.to_string(),
                kind: MEMORY_KIND_GROUP_CAPABILITY.to_string(),
                content,
                source_message_id: None,
                weight: 0.4,
                pinned: false,
                tier: crate::memory_tier::TIER_RAW.to_string(),
                scope: SCOPE_GROUP.to_string(),
                scope_ref: Some(group_id.to_string()),
                importance: 0,
                status: crate::memory_tier::STATUS_ACTIVE.to_string(),
                title: Some(friend_id),
                summary: None,
                expires_at: None,
                workspace_id: None,
            })
            .await?;
    }
    Ok(())
}

/// 归档超出保留上限的旧 raw 表现摘录（减轻库膨胀）。
pub async fn archive_excess_group_capability_raw(
    store: &SqliteStore,
    assistant_owner_id: &str,
    group_id: &str,
) -> Result<u32> {
    let rows = store
        .list_group_capability_raw(assistant_owner_id, group_id, 256)
        .await?;
    let mut archived = 0u32;
    for m in rows
        .iter()
        .skip(MAX_GROUP_CAPABILITY_RAW_PER_GROUP as usize)
    {
        if store
            .update_memory(
                &m.id,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                Some(crate::memory_tier::STATUS_ARCHIVED),
                None,
                None,
                false,
            )
            .await
            .is_ok()
        {
            archived += 1;
        }
    }
    Ok(archived)
}

/// 各成员最近一条 raw 表现摘录（供 roster 专长行）。
pub async fn member_recent_capability_hints(
    store: &SqliteStore,
    assistant_owner_id: &str,
    group_id: &str,
    members: &[crate::domain::Friend],
) -> Result<std::collections::HashMap<String, String>> {
    use std::collections::HashMap;

    let rows = store
        .list_group_capability_raw(assistant_owner_id, group_id, 64)
        .await?;
    let mut out = HashMap::new();
    for f in members {
        let Some(m) = rows
            .iter()
            .find(|r| r.title.as_deref() == Some(f.id.as_str()))
        else {
            continue;
        };
        let hint = m
            .content
            .lines()
            .filter(|l| !l.trim().is_empty() && !l.starts_with("群成员表现"))
            .last()
            .map(|l| truncate_chars(l.trim(), 80))
            .unwrap_or_else(|| truncate_chars(m.content.trim(), 80));
        if !hint.is_empty() {
            out.insert(f.id.clone(), hint);
        }
    }
    Ok(out)
}

pub async fn format_group_capability_excerpt(
    store: &SqliteStore,
    assistant_owner_id: &str,
    group_id: &str,
    limit: i64,
) -> Result<String> {
    let rows = store
        .list_memories_filtered(
            assistant_owner_id,
            ListMemoryFilter {
                tier: None,
                status: Some(crate::memory_tier::STATUS_ACTIVE.to_string()),
                scope: Some(SCOPE_GROUP.to_string()),
                category: None,
            },
            limit * 3,
        )
        .await?;
    let mut lines: Vec<String> = rows
        .into_iter()
        .filter(|m| m.kind == MEMORY_KIND_GROUP_CAPABILITY)
        .filter(|m| m.scope_ref.as_deref() == Some(group_id))
        .take(limit as usize)
        .map(|m| truncate_chars(&m.content, 200))
        .collect();
    if lines.is_empty() {
        return Ok(String::new());
    }
    lines.reverse();
    Ok(format!(
        "近期成员表现摘要（供分工参考）：\n{}",
        lines.join("\n---\n")
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory_tier::{STATUS_ACTIVE, STATUS_ARCHIVED, TIER_RAW};

    #[tokio::test]
    async fn archives_excess_raw_capability_rows() {
        let dir = tempfile::tempdir().expect("tempdir");
        let url = format!(
            "sqlite://{}?mode=rwc",
            dir.path().join("cap.db").display()
        );
        let store = SqliteStore::connect(&url).await.expect("connect");
        store.migrate().await.expect("migrate");
        store.ensure_tenant().await.expect("tenant");
        store
            .upsert_friend(crate::store::friend::UpsertFriend {
                id: Some("asst".into()),
                name: "a".into(),
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

        let gid = "g1";
        for i in 0..52 {
            store
                .insert_memory(crate::store::memory::NewMemory {
                    owner_friend_id: "asst".into(),
                    kind: MEMORY_KIND_GROUP_CAPABILITY.into(),
                    content: format!("raw {i}"),
                    source_message_id: None,
                    weight: 0.4,
                    pinned: false,
                    tier: TIER_RAW.into(),
                    scope: SCOPE_GROUP.into(),
                    scope_ref: Some(gid.into()),
                    importance: 0,
                    status: STATUS_ACTIVE.into(),
                    title: Some(format!("f{i}")),
                    summary: None,
                    expires_at: None,
                    workspace_id: None,
                })
                .await
                .expect("insert");
        }
        let n = archive_excess_group_capability_raw(&store, "asst", gid)
            .await
            .expect("archive");
        assert_eq!(n, 4);
        let active = store
            .list_group_capability_raw("asst", gid, 100)
            .await
            .expect("list");
        assert_eq!(active.len(), 48);
        let archived: (i64,) = sqlx::query_as(
            "SELECT COUNT(*) FROM memories WHERE kind = ? AND scope_ref = ? AND status = ?",
        )
        .bind(MEMORY_KIND_GROUP_CAPABILITY)
        .bind(gid)
        .bind(STATUS_ARCHIVED)
        .fetch_one(store.pool())
        .await
        .expect("count");
        assert_eq!(archived.0, 4);
    }
}
