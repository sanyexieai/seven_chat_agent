use chrono::Utc;
use serde::Deserialize;
use uuid::Uuid;

use crate::cli_workspace;
use crate::domain::{BackendKind, PtyBackendConfig, Workspace};
use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

#[derive(Debug, sqlx::FromRow)]
struct WorkspaceRow {
    id: String,
    tenant_id: String,
    owner_friend_id: String,
    name: String,
    path: String,
    is_default: i64,
    cli_session_mode: Option<String>,
    cli_session_id: Option<String>,
    created_at: String,
    updated_at: String,
}

impl WorkspaceRow {
    fn into_workspace(self) -> Workspace {
        Workspace {
            id: self.id,
            tenant_id: self.tenant_id,
            owner_friend_id: self.owner_friend_id,
            name: self.name,
            path: self.path,
            is_default: self.is_default != 0,
            cli_session_mode: self.cli_session_mode,
            cli_session_id: self.cli_session_id,
            created_at: parse_dt(&self.created_at),
            updated_at: parse_dt(&self.updated_at),
        }
    }
}

const WORKSPACE_SELECT: &str =
    "id, tenant_id, owner_friend_id, name, path, is_default, cli_session_mode, cli_session_id, created_at, updated_at";

#[derive(Debug, Deserialize)]
pub struct CreateWorkspace {
    pub name: String,
    pub path: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateWorkspace {
    pub name: Option<String>,
    pub path: Option<String>,
}

/// 将工作区路径与会话覆盖到 Pty 配置（执行 / 续聊用）。
pub fn apply_workspace_to_pty(cfg: &mut PtyBackendConfig, ws: &Workspace) {
    let path = ws.path.trim();
    if !path.is_empty() {
        cfg.cwd = Some(path.to_string());
    }
    if let Some(mode) = ws
        .cli_session_mode
        .as_deref()
        .filter(|s| !s.trim().is_empty())
    {
        cfg.cli_session_mode = Some(mode.to_string());
    }
    cfg.cli_session_id = ws
        .cli_session_id
        .clone()
        .filter(|s| !s.trim().is_empty());
}

impl SqliteStore {
    pub async fn list_workspaces_for_friend(&self, friend_id: &str) -> Result<Vec<Workspace>> {
        let rows = sqlx::query_as::<_, WorkspaceRow>(&format!(
            "SELECT {WORKSPACE_SELECT} FROM workspaces WHERE tenant_id = ? AND owner_friend_id = ? ORDER BY is_default DESC, created_at ASC"
        ))
        .bind(self.tenant_id())
        .bind(friend_id)
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(|r| r.into_workspace()).collect())
    }

    pub async fn get_workspace(&self, id: &str) -> Result<Option<Workspace>> {
        let row = sqlx::query_as::<_, WorkspaceRow>(&format!(
            "SELECT {WORKSPACE_SELECT} FROM workspaces WHERE id = ? AND tenant_id = ?"
        ))
        .bind(id)
        .bind(self.tenant_id())
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(|r| r.into_workspace()))
    }

    pub async fn get_active_workspace(&self, friend_id: &str) -> Result<Option<Workspace>> {
        let active: Option<String> = sqlx::query_scalar(
            "SELECT active_workspace_id FROM friends WHERE id = ?",
        )
        .bind(friend_id)
        .fetch_optional(self.pool())
        .await?
        .flatten();
        if let Some(id) = active.filter(|s| !s.is_empty()) {
            if let Some(ws) = self.get_workspace(&id).await? {
                return Ok(Some(ws));
            }
        }
        self.default_workspace_for_friend(friend_id).await
    }

    pub async fn default_workspace_for_friend(
        &self,
        friend_id: &str,
    ) -> Result<Option<Workspace>> {
        let row = sqlx::query_as::<_, WorkspaceRow>(&format!(
            "SELECT {WORKSPACE_SELECT} FROM workspaces WHERE tenant_id = ? AND owner_friend_id = ? AND is_default = 1 LIMIT 1"
        ))
        .bind(self.tenant_id())
        .bind(friend_id)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(|r| r.into_workspace()))
    }

    pub async fn set_active_workspace(&self, friend_id: &str, workspace_id: &str) -> Result<()> {
        let ws = self
            .get_workspace(workspace_id)
            .await?
            .ok_or_else(|| Error::not_found("workspace"))?;
        if ws.owner_friend_id != friend_id {
            return Err(Error::bad_request("工作区不属于该好友"));
        }
        sqlx::query("UPDATE friends SET active_workspace_id = ? WHERE id = ?")
            .bind(workspace_id)
            .bind(friend_id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn create_workspace(
        &self,
        friend_id: &str,
        req: CreateWorkspace,
    ) -> Result<Workspace> {
        self.ensure_friend_workspaces(friend_id).await?;
        let name = req.name.trim();
        if name.is_empty() {
            return Err(Error::bad_request("工作区名称不能为空"));
        }
        let id = Uuid::new_v4().to_string();
        let path = if let Some(p) = req.path.as_deref().map(str::trim).filter(|s| !s.is_empty()) {
            cli_workspace::ensure_at(p)?
        } else {
            let sub = format!("{friend_id}/{id}");
            let raw = cli_workspace::workspace_root().join(sub);
            cli_workspace::ensure_workspace(&raw, true)?;
            cli_workspace::absolutize_path(&raw)?.to_string_lossy().into_owned()
        };
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            r#"INSERT INTO workspaces (id, tenant_id, owner_friend_id, name, path, is_default, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0, ?, ?)"#,
        )
        .bind(&id)
        .bind(self.tenant_id())
        .bind(friend_id)
        .bind(name)
        .bind(&path)
        .bind(&now)
        .bind(&now)
        .execute(self.pool())
        .await?;
        let ws = self
            .get_workspace(&id)
            .await?
            .ok_or_else(|| Error::not_found("workspace after insert"))?;
        let active: Option<String> = sqlx::query_scalar(
            "SELECT active_workspace_id FROM friends WHERE id = ?",
        )
        .bind(friend_id)
        .fetch_one(self.pool())
        .await?;
        if active.is_none() {
            self.set_active_workspace(friend_id, &id).await?;
        }
        Ok(ws)
    }

    pub async fn update_workspace(&self, workspace_id: &str, req: UpdateWorkspace) -> Result<Workspace> {
        let existing = self
            .get_workspace(workspace_id)
            .await?
            .ok_or_else(|| Error::not_found("workspace"))?;
        let name = req
            .name
            .as_deref()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .unwrap_or(existing.name.as_str());
        let path = if let Some(p) = req.path.as_deref().map(str::trim).filter(|s| !s.is_empty()) {
            cli_workspace::ensure_at(p)?
        } else {
            existing.path
        };
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "UPDATE workspaces SET name = ?, path = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
        )
        .bind(name)
        .bind(&path)
        .bind(&now)
        .bind(workspace_id)
        .bind(self.tenant_id())
        .execute(self.pool())
        .await?;
        self.get_workspace(workspace_id)
            .await?
            .ok_or_else(|| Error::not_found("workspace after update"))
    }

    pub async fn delete_workspace(&self, workspace_id: &str) -> Result<()> {
        let ws = self
            .get_workspace(workspace_id)
            .await?
            .ok_or_else(|| Error::not_found("workspace"))?;
        if ws.is_default {
            return Err(Error::bad_request("不能删除默认工作区"));
        }
        let count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM workspaces WHERE tenant_id = ? AND owner_friend_id = ?",
        )
        .bind(self.tenant_id())
        .bind(&ws.owner_friend_id)
        .fetch_one(self.pool())
        .await?;
        if count <= 1 {
            return Err(Error::bad_request("至少保留一个工作区"));
        }
        let active: Option<String> = sqlx::query_scalar(
            "SELECT active_workspace_id FROM friends WHERE id = ?",
        )
        .bind(&ws.owner_friend_id)
        .fetch_one(self.pool())
        .await?;
        sqlx::query("DELETE FROM workspaces WHERE id = ? AND tenant_id = ?")
            .bind(workspace_id)
            .bind(self.tenant_id())
            .execute(self.pool())
            .await?;
        if active.as_deref() == Some(workspace_id) {
            if let Some(def) = self.default_workspace_for_friend(&ws.owner_friend_id).await? {
                let _ = self
                    .set_active_workspace(&ws.owner_friend_id, &def.id)
                    .await;
            }
        }
        Ok(())
    }

    pub async fn patch_workspace_cli_session(
        &self,
        workspace_id: &str,
        session_id: Option<String>,
        session_mode: Option<String>,
    ) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        let sid = session_id.filter(|s| !s.trim().is_empty());
        sqlx::query(
            r#"UPDATE workspaces SET cli_session_id = ?, cli_session_mode = COALESCE(?, cli_session_mode), updated_at = ?
               WHERE id = ? AND tenant_id = ?"#,
        )
        .bind(&sid)
        .bind(session_mode.as_deref())
        .bind(&now)
        .bind(workspace_id)
        .bind(self.tenant_id())
        .execute(self.pool())
        .await?;
        Ok(())
    }

    /// 确保好友至少有一个默认工作区（幂等）；从 legacy `backend_config.cwd` 迁移。
    pub async fn ensure_friend_workspaces(&self, friend_id: &str) -> Result<()> {
        let friend = self
            .get_friend(friend_id)
            .await?
            .ok_or_else(|| Error::not_found(format!("friend {friend_id}")))?;
        if friend.backend_kind == BackendKind::Human {
            return Ok(());
        }
        let existing: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM workspaces WHERE tenant_id = ? AND owner_friend_id = ?",
        )
        .bind(self.tenant_id())
        .bind(friend_id)
        .fetch_one(self.pool())
        .await?;
        if existing > 0 {
            return Ok(());
        }
        let cfg: PtyBackendConfig =
            serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
        let path = if let Some(ref p) = cfg.cwd {
            let t = p.trim();
            if !t.is_empty() {
                cli_workspace::ensure_at(t)?
            } else {
                cli_workspace::ensure_for_friend(friend_id)?
            }
        } else {
            cli_workspace::ensure_for_friend(friend_id)?
        };
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            r#"INSERT INTO workspaces (id, tenant_id, owner_friend_id, name, path, is_default,
               cli_session_mode, cli_session_id, created_at, updated_at)
               VALUES (?, ?, ?, '默认', ?, 1, ?, ?, ?, ?)"#,
        )
        .bind(&id)
        .bind(self.tenant_id())
        .bind(friend_id)
        .bind(&path)
        .bind(cfg.cli_session_mode.as_deref())
        .bind(cfg.cli_session_id.as_deref())
        .bind(&now)
        .bind(&now)
        .execute(self.pool())
        .await?;
        sqlx::query(
            "UPDATE friends SET active_workspace_id = COALESCE(active_workspace_id, ?) WHERE id = ?",
        )
        .bind(&id)
        .bind(friend_id)
        .execute(self.pool())
        .await?;
        Ok(())
    }

    pub async fn migrate_all_friend_workspaces(&self) -> Result<()> {
        let ids: Vec<String> = sqlx::query_scalar(
            "SELECT id FROM friends WHERE backend_kind != 'human'",
        )
        .fetch_all(self.pool())
        .await?;
        for id in ids {
            if let Err(e) = self.ensure_friend_workspaces(&id).await {
                tracing::warn!(friend_id = %id, err = %e, "ensure_friend_workspaces failed");
            }
        }
        Ok(())
    }

    /// 私聊消息关联的工作区：对端好友的当前 active workspace。
    pub async fn workspace_id_for_dm_conversation(
        &self,
        conversation_id: &str,
    ) -> Result<Option<String>> {
        let row: Option<(String, String)> = sqlx::query_as(
            "SELECT kind, target_id FROM conversations WHERE id = ?",
        )
        .bind(conversation_id)
        .fetch_optional(self.pool())
        .await?;
        let Some((kind, target_id)) = row else {
            return Ok(None);
        };
        if kind != "dm" {
            return Ok(None);
        }
        self.ensure_friend_workspaces(&target_id).await.ok();
        Ok(self
            .get_active_workspace(&target_id)
            .await?
            .map(|w| w.id))
    }
}
