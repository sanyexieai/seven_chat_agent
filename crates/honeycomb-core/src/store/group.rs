use std::collections::HashMap;

use chrono::Utc;
use honeycomb_judge::MemberJudgeOverride;
use uuid::Uuid;

use crate::domain::{Group, GroupMemberConfig, GroupSettings};
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
        let rows: Vec<(String, Option<String>)> = sqlx::query_as(
            "SELECT friend_id, judge_override FROM group_members WHERE group_id = ? AND role <> 'muted'",
        )
        .bind(group_id)
        .fetch_all(self.pool())
        .await?;
        Ok(rows
            .into_iter()
            .map(|(friend_id, judge_raw)| GroupMemberConfig {
                friend_id,
                judge_override: judge_raw
                    .as_deref()
                    .and_then(|s| serde_json::from_str(s).ok()),
            })
            .collect())
    }

    pub async fn upsert_group(&self, req: UpsertGroup) -> Result<Group> {
        let id = req.id.unwrap_or_else(|| Uuid::new_v4().to_string());
        let mut settings = req.settings;
        settings.sync_judge_threshold_fields();
        let settings_json = serde_json::to_string(&settings)?;
        let now = Utc::now().to_rfc3339();

        let legacy_only = req.members.is_empty() && !req.member_ids.is_empty();
        let members = normalize_group_members(req.members, req.member_ids);

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

        let preserved: HashMap<String, Option<MemberJudgeOverride>> = self
            .list_group_member_configs(&id)
            .await?
            .into_iter()
            .map(|m| (m.friend_id, m.judge_override))
            .collect();

        sqlx::query("DELETE FROM group_members WHERE group_id = ?")
            .bind(&id)
            .execute(self.pool())
            .await?;

        for m in &members {
            let judge_override = if legacy_only {
                preserved.get(&m.friend_id).cloned().flatten()
            } else {
                m.judge_override.clone()
            };
            let judge_json = judge_override
                .as_ref()
                .map(serde_json::to_string)
                .transpose()?;
            sqlx::query(
                "INSERT OR IGNORE INTO group_members (group_id, friend_id, role, judge_override) VALUES (?, ?, 'member', ?)",
            )
            .bind(&id)
            .bind(&m.friend_id)
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
            judge_override: None,
        })
        .collect()
}
