use chrono::Utc;
use uuid::Uuid;

use crate::domain::{GroupMemberBinding, GroupWorkspace};
use crate::store::{parse_dt, SqliteStore};
use crate::Result;

#[derive(Debug, serde::Deserialize)]
pub struct UpsertGroupWorkspace {
    pub id: Option<String>,
    pub name: String,
    #[serde(default = "default_kind")]
    pub kind: String,
    pub git_url: Option<String>,
    pub default_branch: Option<String>,
    pub logical_key: Option<String>,
}

fn default_kind() -> String {
    "logical".into()
}

#[derive(Debug, serde::Deserialize)]
pub struct UpsertGroupMemberBinding {
    pub id: Option<String>,
    pub group_workspace_id: String,
    pub friend_id: String,
    pub execution_mode: Option<String>,
    pub relay_id: Option<String>,
    pub local_path: Option<String>,
}

#[derive(Debug, sqlx::FromRow)]
struct GroupWorkspaceRow {
    id: String,
    group_id: String,
    tenant_id: String,
    name: String,
    kind: String,
    git_url: Option<String>,
    default_branch: Option<String>,
    logical_key: Option<String>,
    created_at: String,
}

impl GroupWorkspaceRow {
    fn into_workspace(self) -> GroupWorkspace {
        GroupWorkspace {
            id: self.id,
            group_id: self.group_id,
            tenant_id: self.tenant_id,
            name: self.name,
            kind: self.kind,
            git_url: self.git_url,
            default_branch: self.default_branch,
            logical_key: self.logical_key,
            created_at: parse_dt(&self.created_at),
        }
    }
}

#[derive(Debug, sqlx::FromRow)]
struct GroupMemberBindingRow {
    id: String,
    group_id: String,
    group_workspace_id: String,
    friend_id: String,
    execution_mode: Option<String>,
    relay_id: Option<String>,
    local_path: Option<String>,
}

impl GroupMemberBindingRow {
    fn into_binding(self) -> GroupMemberBinding {
        GroupMemberBinding {
            id: self.id,
            group_id: self.group_id,
            group_workspace_id: self.group_workspace_id,
            friend_id: self.friend_id,
            execution_mode: self.execution_mode,
            relay_id: self.relay_id,
            local_path: self.local_path,
        }
    }
}

impl SqliteStore {
    pub async fn list_group_workspaces(&self, group_id: &str) -> Result<Vec<GroupWorkspace>> {
        let rows = sqlx::query_as::<_, GroupWorkspaceRow>(
            "SELECT id, group_id, tenant_id, name, kind, git_url, default_branch, logical_key, created_at \
             FROM group_workspaces WHERE group_id = ? AND tenant_id = ? ORDER BY created_at ASC",
        )
        .bind(group_id)
        .bind(self.tenant_id())
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(|r| r.into_workspace()).collect())
    }

    pub async fn list_group_member_bindings(
        &self,
        group_id: &str,
    ) -> Result<Vec<GroupMemberBinding>> {
        let rows = sqlx::query_as::<_, GroupMemberBindingRow>(
            "SELECT id, group_id, group_workspace_id, friend_id, execution_mode, relay_id, local_path \
             FROM group_member_bindings WHERE group_id = ? ORDER BY friend_id ASC",
        )
        .bind(group_id)
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(|r| r.into_binding()).collect())
    }

    /// 解析成员在群内的执行 cwd（优先主工作区 binding.local_path）。
    pub async fn resolve_member_group_local_path(
        &self,
        group_id: &str,
        friend_id: &str,
    ) -> Result<Option<String>> {
        let row: Option<(Option<String>,)> = sqlx::query_as(
            "SELECT b.local_path FROM group_member_bindings b \
             JOIN group_workspaces w ON w.id = b.group_workspace_id \
             WHERE b.group_id = ? AND b.friend_id = ? AND w.tenant_id = ? \
             ORDER BY w.created_at ASC LIMIT 1",
        )
        .bind(group_id)
        .bind(friend_id)
        .bind(self.tenant_id())
        .fetch_optional(self.pool())
        .await?;
        Ok(row.and_then(|(p,)| p).filter(|s| !s.trim().is_empty()))
    }

    pub async fn sync_group_workspaces_and_bindings(
        &self,
        group_id: &str,
        workspaces: &[UpsertGroupWorkspace],
        bindings: &[UpsertGroupMemberBinding],
    ) -> Result<()> {
        if workspaces.is_empty() && bindings.is_empty() {
            return Ok(());
        }

        let now = Utc::now().to_rfc3339();
        let mut ws_id_map: std::collections::HashMap<String, String> =
            std::collections::HashMap::new();

        sqlx::query("DELETE FROM group_member_bindings WHERE group_id = ?")
            .bind(group_id)
            .execute(self.pool())
            .await?;
        sqlx::query(
            "DELETE FROM group_workspaces WHERE group_id = ? AND tenant_id = ?",
        )
        .bind(group_id)
        .bind(self.tenant_id())
        .execute(self.pool())
        .await?;

        for ws in workspaces {
            let id = ws.id.clone().unwrap_or_else(|| Uuid::new_v4().to_string());
            if let Some(ref key) = ws.logical_key {
                ws_id_map.insert(key.clone(), id.clone());
            }
            ws_id_map.insert(ws.name.clone(), id.clone());
            sqlx::query(
                "INSERT INTO group_workspaces \
                 (id, group_id, tenant_id, name, kind, git_url, default_branch, logical_key, created_at) \
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            )
            .bind(&id)
            .bind(group_id)
            .bind(self.tenant_id())
            .bind(&ws.name)
            .bind(&ws.kind)
            .bind(&ws.git_url)
            .bind(&ws.default_branch)
            .bind(&ws.logical_key)
            .bind(&now)
            .execute(self.pool())
            .await?;
        }

        for b in bindings {
            let ws_id = ws_id_map
                .get(&b.group_workspace_id)
                .cloned()
                .unwrap_or_else(|| b.group_workspace_id.clone());
            let id = b.id.clone().unwrap_or_else(|| Uuid::new_v4().to_string());
            sqlx::query(
                "INSERT INTO group_member_bindings \
                 (id, group_id, group_workspace_id, friend_id, execution_mode, relay_id, local_path) \
                 VALUES (?, ?, ?, ?, ?, ?, ?)",
            )
            .bind(&id)
            .bind(group_id)
            .bind(&ws_id)
            .bind(&b.friend_id)
            .bind(&b.execution_mode)
            .bind(&b.relay_id)
            .bind(&b.local_path)
            .execute(self.pool())
            .await?;
        }

        Ok(())
    }
}
