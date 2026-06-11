use crate::assistant_accumulation::truncate_chars;
use crate::memory_tier::{
    MEMORY_KIND_MEMBER_GROUP_NOTE, SCOPE_FRIEND, STATUS_ACTIVE, TIER_CURATED,
};
use crate::store::memory::NewMemory;
use crate::store::SqliteStore;
use crate::Result;

pub fn extract_member_group_note(reply: &str) -> Option<String> {
    let t = reply.trim();
    if t.chars().count() < 12 {
        return None;
    }
    Some(truncate_chars(t, 160))
}

/// 成员在本群的发言自述（仅本人 prompt recall；`summary` 存群 id）。
pub async fn record_member_group_note(
    store: &SqliteStore,
    member_id: &str,
    group_id: &str,
    turn_id: &str,
    reply_content: &str,
) -> Result<()> {
    let Some(note) = extract_member_group_note(reply_content) else {
        return Ok(());
    };
    let turn_tag = &turn_id[..turn_id.len().min(8)];
    store
        .insert_memory(NewMemory {
            owner_friend_id: member_id.to_string(),
            kind: MEMORY_KIND_MEMBER_GROUP_NOTE.to_string(),
            content: format!("本群自述（turn={turn_tag}）\n{note}"),
            source_message_id: None,
            weight: 0.55,
            pinned: false,
            tier: TIER_CURATED.to_string(),
            scope: SCOPE_FRIEND.to_string(),
            scope_ref: Some(member_id.to_string()),
            importance: 1,
            status: STATUS_ACTIVE.to_string(),
            title: Some(turn_tag.to_string()),
            summary: Some(group_id.to_string()),
            expires_at: None,
            workspace_id: None,
        })
        .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory_tier::RecallContext;

    #[test]
    fn skips_trivial_reply() {
        assert!(extract_member_group_note("好的").is_none());
        assert!(extract_member_group_note("这是一条足够长的成员自述回复").is_some());
    }

    #[tokio::test]
    async fn member_note_recall_scoped_to_group() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("note.db");
        let url = format!("sqlite://{}?mode=rwc", path.display());
        let store = SqliteStore::connect(&url).await.expect("connect");
        store.migrate().await.expect("migrate");
        store.ensure_tenant().await.expect("tenant");
        for (id, name) in [("m1", "甲"), ("m2", "乙")] {
            store
                .upsert_friend(crate::store::friend::UpsertFriend {
                    id: Some(id.into()),
                    name: name.into(),
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
        }
        record_member_group_note(
            &store,
            "m1",
            "group-a",
            "turn-1",
            "我在 group-a 负责接口联调与错误处理策略",
        )
        .await
        .expect("note");
        record_member_group_note(
            &store,
            "m1",
            "group-b",
            "turn-2",
            "我在 group-b 负责前端状态管理与组件拆分",
        )
        .await
        .expect("note");

        let ctx_a = RecallContext {
            conversation_id: Some("c".into()),
            friend_id: Some("m1".into()),
            workspace_id: None,
            group_id: Some("group-a".into()),
        };
        let hits_a = store
            .recall_memories_for_turn("m1", "联调", 5, false, &ctx_a)
            .await
            .expect("recall");
        assert!(hits_a.iter().any(|m| m.content.contains("group-a")));
        assert!(!hits_a.iter().any(|m| m.content.contains("group-b")));

        let ctx_b = RecallContext {
            group_id: Some("group-b".into()),
            ..ctx_a.clone()
        };
        let hits_b = store
            .recall_memories_for_turn("m1", "前端", 5, false, &ctx_b)
            .await
            .expect("recall");
        assert!(hits_b.iter().any(|m| m.content.contains("group-b")));
    }
}
