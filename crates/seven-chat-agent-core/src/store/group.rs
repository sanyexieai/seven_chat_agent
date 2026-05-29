use std::collections::HashMap;

use chrono::Utc;
use seven_chat_agent_judge::MemberJudgeOverride;
use uuid::Uuid;

use crate::domain::{
    Group, GroupMemberConfig, GroupMemberRole, GroupSettings, BUILTIN_HEX_ASSISTANT_ID,
};
use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

#[derive(Debug, sqlx::FromRow)]
struct GroupRow {
    id: String,
    name: String,
    avatar: Option<String>,
    settings: String,
    created_at: String,
}

impl GroupRow {
    fn into_group(self) -> Result<Group> {
        let settings: GroupSettings =
            serde_json::from_str(&self.settings).unwrap_or_default();
        Ok(Group {
            id: self.id,
            name: self.name,
            avatar: self.avatar,
            settings,
            created_at: parse_dt(&self.created_at),
        })
    }
}

#[derive(Debug, serde::Deserialize)]
pub struct UpsertGroup {
    pub id: Option<String>,
    pub name: String,
    pub avatar: Option<String>,
    #[serde(default)]
    pub settings: GroupSettings,
    /// 新 API：成员 + 本群 Judge 覆盖。
    #[serde(default)]
    pub members: Vec<GroupMemberConfig>,
    /// 兼容旧前端：仅成员 id 列表。
    #[serde(default)]
    pub member_ids: Vec<String>,
}

impl SqliteStore {
    pub async fn list_groups(&self) -> Result<Vec<Group>> {
        let rows = sqlx::query_as::<_, GroupRow>(
            "SELECT id, name, avatar, settings, created_at FROM groups ORDER BY created_at DESC",
        )
        .fetch_all(self.pool())
        .await?;
        rows.into_iter().map(|r| r.into_group()).collect()
    }

    pub async fn get_group(&self, id: &str) -> Result<Option<Group>> {
        let row = sqlx::query_as::<_, GroupRow>(
            "SELECT id, name, avatar, settings, created_at FROM groups WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(self.pool())
        .await?;
        row.map(|r| r.into_group()).transpose()
    }

    /// 解析内置 Hex 助理 id（稳定 id 或最早 builtin）。
    pub async fn builtin_assistant_id(&self) -> Result<Option<String>> {
        if self.get_friend(BUILTIN_HEX_ASSISTANT_ID).await?.is_some() {
            return Ok(Some(BUILTIN_HEX_ASSISTANT_ID.to_string()));
        }
        let row: Option<(String,)> = sqlx::query_as(
            "SELECT id FROM friends WHERE is_builtin = 1 ORDER BY created_at ASC LIMIT 1",
        )
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(|(id,)| id))
    }

    pub async fn list_group_members(&self, group_id: &str) -> Result<Vec<String>> {
        let rows: Vec<(String,)> = sqlx::query_as(
            "SELECT friend_id FROM group_members WHERE group_id = ? AND role <> 'muted'",
        )
        .bind(group_id)
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(|(s,)| s).collect())
    }

    pub async fn list_group_member_configs(
        &self,
        group_id: &str,
    ) -> Result<Vec<GroupMemberConfig>> {
        let rows: Vec<(String, String, Option<String>)> = sqlx::query_as(
            "SELECT friend_id, role, judge_override FROM group_members WHERE group_id = ? AND role <> 'muted'",
        )
        .bind(group_id)
        .fetch_all(self.pool())
        .await?;
        Ok(rows
            .into_iter()
            .map(|(friend_id, role, judge_raw)| GroupMemberConfig {
                friend_id,
                role: GroupMemberRole::parse(&role),
                judge_override: judge_raw
                    .as_deref()
                    .and_then(|s| serde_json::from_str(s).ok()),
            })
            .collect())
    }

    pub async fn list_group_expert_friend_ids(&self, group_id: &str) -> Result<Vec<String>> {
        Ok(self
            .list_group_member_configs(group_id)
            .await?
            .into_iter()
            .filter(|m| m.role.participates_in_expert_scheduling())
            .map(|m| m.friend_id)
            .collect())
    }

    pub async fn group_assistant_member_id(&self, group_id: &str) -> Result<Option<String>> {
        Ok(self
            .list_group_member_configs(group_id)
            .await?
            .into_iter()
            .find(|m| m.role == GroupMemberRole::Assistant)
            .map(|m| m.friend_id))
    }

    /// 为所有群补齐助理成员（启动迁移）。
    pub async fn migrate_ensure_group_assistants(&self) -> Result<()> {
        let Some(assistant_id) = self.builtin_assistant_id().await? else {
            return Ok(());
        };
        let groups = self.list_groups().await?;
        for g in groups {
            let has = self.group_assistant_member_id(&g.id).await?.is_some();
            if has {
                continue;
            }
            sqlx::query(
                "INSERT OR IGNORE INTO group_members (group_id, friend_id, role, judge_override) VALUES (?, ?, 'assistant', NULL)",
            )
            .bind(&g.id)
            .bind(&assistant_id)
            .execute(self.pool())
            .await?;
            tracing::info!(group_id = %g.id, assistant_id = %assistant_id, "migrate: added group assistant member");
        }
        Ok(())
    }

    pub async fn upsert_group(&self, req: UpsertGroup) -> Result<Group> {
        let id = req.id.unwrap_or_else(|| Uuid::new_v4().to_string());
        let mut settings = req.settings;
        settings.sync_judge_threshold_fields();
        let settings_json = serde_json::to_string(&settings)?;
        let now = Utc::now().to_rfc3339();

        let legacy_only = req.members.is_empty() && !req.member_ids.is_empty();
        let mut members = normalize_group_members(req.members, req.member_ids);
        if let Some(aid) = self.builtin_assistant_id().await? {
            ensure_assistant_in_members(&mut members, &aid);
        }

        let exists: i64 = sqlx::query_scalar("SELECT COUNT(1) FROM groups WHERE id = ?")
            .bind(&id)
            .fetch_one(self.pool())
            .await?;
        if exists == 0 {
            sqlx::query(
                "INSERT INTO groups (id, name, avatar, settings, created_at) VALUES (?, ?, ?, ?, ?)",
            )
            .bind(&id)
            .bind(&req.name)
            .bind(&req.avatar)
            .bind(&settings_json)
            .bind(&now)
            .execute(self.pool())
            .await?;
        } else {
            sqlx::query("UPDATE groups SET name=?, avatar=?, settings=? WHERE id = ?")
                .bind(&req.name)
                .bind(&req.avatar)
                .bind(&settings_json)
                .bind(&id)
                .execute(self.pool())
                .await?;
        }

        let preserved: HashMap<String, (GroupMemberRole, Option<MemberJudgeOverride>)> = self
            .list_group_member_configs(&id)
            .await?
            .into_iter()
            .map(|m| (m.friend_id, (m.role, m.judge_override)))
            .collect();

        sqlx::query("DELETE FROM group_members WHERE group_id = ?")
            .bind(&id)
            .execute(self.pool())
            .await?;

        for m in &members {
            let role = if legacy_only {
                preserved
                    .get(&m.friend_id)
                    .map(|(r, _)| *r)
                    .unwrap_or(m.role)
            } else {
                m.role
            };
            let judge_override = if legacy_only {
                preserved.get(&m.friend_id).and_then(|(_, j)| j.clone())
            } else {
                m.judge_override.clone()
            };
            let judge_json = judge_override
                .as_ref()
                .map(serde_json::to_string)
                .transpose()?;
            sqlx::query(
                "INSERT OR IGNORE INTO group_members (group_id, friend_id, role, judge_override) VALUES (?, ?, ?, ?)",
            )
            .bind(&id)
            .bind(&m.friend_id)
            .bind(role.as_str())
            .bind(&judge_json)
            .execute(self.pool())
            .await?;
        }

        self.get_or_create_group_conversation(&id).await?;

        self.get_group(&id)
            .await?
            .ok_or_else(|| Error::not_found("group after upsert"))
    }

    pub async fn get_or_create_group_conversation(
        &self,
        group_id: &str,
    ) -> Result<crate::domain::Conversation> {
        let existing = sqlx::query_scalar::<_, String>(
            "SELECT id FROM conversations WHERE kind = 'group' AND target_id = ?",
        )
        .bind(group_id)
        .fetch_optional(self.pool())
        .await?;
        if let Some(id) = existing {
            return self
                .get_conversation(&id)
                .await?
                .ok_or_else(|| Error::not_found("group conversation"));
        }
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "INSERT INTO conversations (id, kind, target_id, created_at) VALUES (?, 'group', ?, ?)",
        )
        .bind(&id)
        .bind(group_id)
        .bind(&now)
        .execute(self.pool())
        .await?;
        self.get_conversation(&id)
            .await?
            .ok_or_else(|| Error::not_found("group conversation after insert"))
    }
}

fn normalize_group_members(
    members: Vec<GroupMemberConfig>,
    member_ids: Vec<String>,
) -> Vec<GroupMemberConfig> {
    if !members.is_empty() {
        return members;
    }
    member_ids
        .into_iter()
        .map(|friend_id| GroupMemberConfig {
            friend_id,
            role: GroupMemberRole::Member,
            judge_override: None,
        })
        .collect()
}

fn ensure_assistant_in_members(members: &mut Vec<GroupMemberConfig>, assistant_id: &str) {
    let mut found_assistant_role = false;
    for m in members.iter_mut() {
        if m.friend_id == assistant_id {
            m.role = GroupMemberRole::Assistant;
            found_assistant_role = true;
        } else if m.role == GroupMemberRole::Assistant {
            m.role = GroupMemberRole::Member;
        }
    }
    if !found_assistant_role {
        members.push(GroupMemberConfig {
            friend_id: assistant_id.to_string(),
            role: GroupMemberRole::Assistant,
            judge_override: None,
        });
    }
}
