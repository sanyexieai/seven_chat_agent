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
    owner_user_id: Option<String>,
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
            owner_user_id: self.owner_user_id,
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

const WORKSPACE_SELECT: &str = "id, tenant_id, owner_friend_id, owner_user_id, name, path, is_default, cli_session_mode, cli_session_id, created_at, updated_at";

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
        let use_path = if crate::friend_cli::pty_execution_is_relay(cfg) {
            !crate::friend_cli::looks_like_server_cli_workspace(path)
        } else {
            true
        };
        if use_path {
            cfg.cwd = Some(path.to_string());
        }
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
    fn workspace_owner_sql(&self) -> &'static str {
        if self.is_user_scoped() {
            " AND owner_user_id = ?"
        } else {
            " AND owner_user_id IS NULL"
        }
    }

    fn workspace_owned_by(&self, ws: &Workspace) -> bool {
        match (&self.user_id, &ws.owner_user_id) {
            (Some(uid), Some(wuid)) => uid == wuid,
            (None, None) => true,
            _ => false,
        }
    }

    pub async fn active_workspace_id_for_friend(
        &self,
        friend_id: &str,
    ) -> Result<Option<String>> {
        if let Some(uid) = self.user_id.as_deref() {
            let id: Option<String> = sqlx::query_scalar(
                "SELECT active_workspace_id FROM user_workspace_prefs WHERE user_id = ? AND friend_id = ?",
            )
            .bind(uid)
            .bind(friend_id)
            .fetch_optional(self.pool())
            .await?
            .flatten();
            if id.is_some() {
                return Ok(id);
            }
        } else {
            let id: Option<String> = sqlx::query_scalar(
                "SELECT active_workspace_id FROM friends WHERE id = ?",
            )
            .bind(friend_id)
            .fetch_optional(self.pool())
            .await?
            .flatten();
            if id.is_some() {
                return Ok(id);
            }
        }
        Ok(self
            .default_workspace_for_friend(friend_id)
            .await?
            .map(|w| w.id))
    }

    pub async fn list_workspaces_for_friend(&self, friend_id: &str) -> Result<Vec<Workspace>> {
        let sql = format!(
            "SELECT {WORKSPACE_SELECT} FROM workspaces WHERE tenant_id = ? AND owner_friend_id = ?{} ORDER BY is_default DESC, created_at ASC",
            self.workspace_owner_sql()
        );
        let mut q = sqlx::query_as::<_, WorkspaceRow>(&sql)
            .bind(self.tenant_id())
            .bind(friend_id);
        if let Some(uid) = self.user_id.as_deref() {
            q = q.bind(uid);
        }
        let rows = q.fetch_all(self.pool()).await?;
        Ok(rows.into_iter().map(|r| r.into_workspace()).collect())
    }

    pub async fn get_workspace(&self, id: &str) -> Result<Option<Workspace>> {
        let sql = format!(
            "SELECT {WORKSPACE_SELECT} FROM workspaces WHERE id = ? AND tenant_id = ?{}",
            self.workspace_owner_sql()
        );
        let mut q = sqlx::query_as::<_, WorkspaceRow>(&sql)
            .bind(id)
            .bind(self.tenant_id());
        if let Some(uid) = self.user_id.as_deref() {
            q = q.bind(uid);
        }
        let row = q.fetch_optional(self.pool()).await?;
        Ok(row.map(|r| r.into_workspace()))
    }

    pub async fn get_active_workspace(&self, friend_id: &str) -> Result<Option<Workspace>> {
        if let Some(id) = self
            .active_workspace_id_for_friend(friend_id)
            .await?
            .filter(|s| !s.is_empty())
        {
            if let Some(ws) = self.get_workspace(&id).await? {
                if ws.owner_friend_id == friend_id {
                    return Ok(Some(ws));
                }
            }
        }
        self.default_workspace_for_friend(friend_id).await
    }

    pub async fn default_workspace_for_friend(
        &self,
        friend_id: &str,
    ) -> Result<Option<Workspace>> {
        let sql = format!(
            "SELECT {WORKSPACE_SELECT} FROM workspaces WHERE tenant_id = ? AND owner_friend_id = ? AND is_default = 1{} LIMIT 1",
            self.workspace_owner_sql()
        );
        let mut q = sqlx::query_as::<_, WorkspaceRow>(&sql)
            .bind(self.tenant_id())
            .bind(friend_id);
        if let Some(uid) = self.user_id.as_deref() {
            q = q.bind(uid);
        }
        let row = q.fetch_optional(self.pool()).await?;
        Ok(row.map(|r| r.into_workspace()))
    }

    async fn upsert_user_active_workspace(
        &self,
        friend_id: &str,
        workspace_id: &str,
    ) -> Result<()> {
        let uid = self
            .user_id
            .as_deref()
            .ok_or_else(|| Error::bad_request("需要登录用户才能切换工作区"))?;
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            r#"INSERT INTO user_workspace_prefs (user_id, friend_id, active_workspace_id, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, friend_id) DO UPDATE SET
                 active_workspace_id = excluded.active_workspace_id,
                 updated_at = excluded.updated_at"#,
        )
        .bind(uid)
        .bind(friend_id)
        .bind(workspace_id)
        .bind(&now)
        .execute(self.pool())
        .await?;
        Ok(())
    }

    pub async fn set_active_workspace(&self, friend_id: &str, workspace_id: &str) -> Result<()> {
        let ws = self
            .get_workspace(workspace_id)
            .await?
            .ok_or_else(|| Error::not_found("workspace"))?;
        if ws.owner_friend_id != friend_id {
            return Err(Error::bad_request("工作区不属于该好友"));
        }
        if !self.workspace_owned_by(&ws) {
            return Err(Error::bad_request("工作区不属于当前用户"));
        }
        if self.is_user_scoped() {
            self.upsert_user_active_workspace(friend_id, workspace_id)
                .await
        } else {
            sqlx::query("UPDATE friends SET active_workspace_id = ? WHERE id = ?")
                .bind(workspace_id)
                .bind(friend_id)
                .execute(self.pool())
                .await?;
            Ok(())
        }
    }

    fn default_workspace_path(&self, friend_id: &str) -> Result<String> {
        if let (Some(uid), _) = (self.user_id.as_deref(), friend_id) {
            cli_workspace::ensure_for_user_friend(self.tenant_id(), uid, friend_id)
        } else {
            cli_workspace::ensure_for_friend(friend_id)
        }
    }

    fn extra_workspace_path(&self, friend_id: &str, workspace_id: &str) -> Result<String> {
        let sub = if let Some(uid) = self.user_id.as_deref() {
            format!("tenants/{}/{uid}/{friend_id}/{workspace_id}", self.tenant_id())
        } else {
            format!("{friend_id}/{workspace_id}")
        };
        let raw = cli_workspace::workspace_root().join(sub);
        cli_workspace::ensure_workspace(&raw, true)?;
        Ok(cli_workspace::absolutize_path(&raw)?.to_string_lossy().into_owned())
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
            self.extra_workspace_path(friend_id, &id)?
        };
        let now = Utc::now().to_rfc3339();
        let owner_user_id = self.user_id.clone();
        sqlx::query(
            r#"INSERT INTO workspaces (id, tenant_id, owner_friend_id, owner_user_id, name, path, is_default, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)"#,
        )
        .bind(&id)
        .bind(self.tenant_id())
        .bind(friend_id)
        .bind(&owner_user_id)
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
        if self.active_workspace_id_for_friend(friend_id).await?.is_none() {
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
        let count_sql = format!(
            "SELECT COUNT(*) FROM workspaces WHERE tenant_id = ? AND owner_friend_id = ?{}",
            self.workspace_owner_sql()
        );
        let mut cq = sqlx::query_scalar::<_, i64>(&count_sql)
            .bind(self.tenant_id())
            .bind(&ws.owner_friend_id);
        if let Some(uid) = self.user_id.as_deref() {
            cq = cq.bind(uid);
        }
        let count = cq.fetch_one(self.pool()).await?;
        if count <= 1 {
            return Err(Error::bad_request("至少保留一个工作区"));
        }
        let active = self
            .active_workspace_id_for_friend(&ws.owner_friend_id)
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
        let count_sql = format!(
            "SELECT COUNT(*) FROM workspaces WHERE tenant_id = ? AND owner_friend_id = ?{}",
            self.workspace_owner_sql()
        );
        let mut q = sqlx::query_scalar::<_, i64>(&count_sql)
            .bind(self.tenant_id())
            .bind(friend_id);
        if let Some(uid) = self.user_id.as_deref() {
            q = q.bind(uid);
        }
        let existing = q.fetch_one(self.pool()).await?;
        if existing > 0 {
            return Ok(());
        }
        let cfg: PtyBackendConfig =
            serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
        let path = if self.is_user_scoped() {
            self.default_workspace_path(friend_id)?
        } else if let Some(ref p) = cfg.cwd {
            let t = p.trim();
            if !t.is_empty() {
                cli_workspace::ensure_at(t)?
            } else {
                self.default_workspace_path(friend_id)?
            }
        } else {
            self.default_workspace_path(friend_id)?
        };
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let owner_user_id = self.user_id.clone();
        sqlx::query(
            r#"INSERT INTO workspaces (id, tenant_id, owner_friend_id, owner_user_id, name, path, is_default,
               cli_session_mode, cli_session_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, '默认', ?, 1, ?, ?, ?, ?)"#,
        )
        .bind(&id)
        .bind(self.tenant_id())
        .bind(friend_id)
        .bind(&owner_user_id)
        .bind(&path)
        .bind(cfg.cli_session_mode.as_deref())
        .bind(cfg.cli_session_id.as_deref())
        .bind(&now)
        .bind(&now)
        .execute(self.pool())
        .await?;
        if self.is_user_scoped() {
            self.upsert_user_active_workspace(friend_id, &id).await?;
        } else {
            sqlx::query(
                "UPDATE friends SET active_workspace_id = COALESCE(active_workspace_id, ?) WHERE id = ?",
            )
            .bind(&id)
            .bind(friend_id)
            .execute(self.pool())
            .await?;
        }
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

    /// 私聊消息关联的工作区：对端好友的当前 active workspace（按请求用户）。
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
