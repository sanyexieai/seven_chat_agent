use chrono::Utc;
use serde_json::Value;
use uuid::Uuid;

use crate::cli_workspace;
use crate::domain::{BackendKind, Friend, PtyBackendConfig};
use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

#[derive(Debug, sqlx::FromRow)]
pub struct FriendRow {
    pub id: String,
    pub name: String,
    pub avatar: Option<String>,
    pub system_prompt: String,
    pub personality: Option<String>,
    pub focus_tags: String,
    pub backend_kind: String,
    pub backend_config: String,
    pub judge_provider_ref: Option<String>,
    pub enabled: i64,
    pub is_builtin: i64,
    pub active_workspace_id: Option<String>,
    pub created_at: String,
}

impl FriendRow {
    pub fn into_friend(self) -> Result<Friend> {
        let kind = BackendKind::parse(&self.backend_kind)
            .ok_or_else(|| Error::Config(format!("unknown backend_kind {}", self.backend_kind)))?;
        let focus_tags: Vec<String> =
            serde_json::from_str(&self.focus_tags).unwrap_or_default();
        let backend_config: Value =
            serde_json::from_str(&self.backend_config).unwrap_or_else(|_| serde_json::json!({}));
        Ok(Friend {
            id: self.id,
            name: self.name,
            avatar: self.avatar,
            system_prompt: self.system_prompt,
            personality: self.personality,
            focus_tags,
            backend_kind: kind,
            backend_config,
            judge_provider_ref: self.judge_provider_ref,
            enabled: self.enabled != 0,
            is_builtin: self.is_builtin != 0,
            active_workspace_id: self.active_workspace_id,
            created_at: parse_dt(&self.created_at),
        })
    }
}

const FRIEND_SELECT: &str = "id, name, avatar, system_prompt, personality, focus_tags, backend_kind, backend_config, judge_provider_ref, enabled, is_builtin, active_workspace_id, created_at";

#[derive(Debug, serde::Deserialize)]
pub struct UpsertFriend {
    pub id: Option<String>,
    pub name: String,
    pub avatar: Option<String>,
    pub system_prompt: String,
    pub personality: Option<String>,
    pub focus_tags: Vec<String>,
    pub backend_kind: BackendKind,
    pub backend_config: Value,
    pub judge_provider_ref: Option<String>,
    #[serde(default = "default_true")]
    pub enabled: bool,
}

fn default_true() -> bool {
    true
}

impl SqliteStore {
    pub async fn list_friends(&self) -> Result<Vec<Friend>> {
        let rows = sqlx::query_as::<_, FriendRow>(&format!(
            "SELECT {FRIEND_SELECT} FROM friends WHERE tenant_id = ? ORDER BY is_builtin DESC, created_at ASC"
        ))
        .bind(self.tenant_id())
        .fetch_all(self.pool())
        .await?;
        rows.into_iter().map(|r| r.into_friend()).collect()
    }

    pub async fn get_friend(&self, id: &str) -> Result<Option<Friend>> {
        let row = sqlx::query_as::<_, FriendRow>(&format!(
            "SELECT {FRIEND_SELECT} FROM friends WHERE id = ? AND tenant_id = ?"
        ))
        .bind(id)
        .bind(self.tenant_id())
        .fetch_optional(self.pool())
        .await?;
        let mut friend = row.map(|r| r.into_friend()).transpose()?;
        if let Some(ref mut f) = friend {
            if self.is_user_scoped() {
                f.active_workspace_id = self.active_workspace_id_for_friend(id).await?;
            }
        }
        Ok(friend)
    }

    pub async fn upsert_friend(&self, req: UpsertFriend) -> Result<Friend> {
        let id = req.id.unwrap_or_else(|| Uuid::new_v4().to_string());
        let focus_tags = serde_json::to_string(&req.focus_tags)?;
        let mut backend_config_value = req.backend_config.clone();

        let exists: i64 =
            sqlx::query_scalar("SELECT COUNT(1) FROM friends WHERE id = ?")
                .bind(&id)
                .fetch_one(self.pool())
                .await?;

        if req.backend_kind == BackendKind::Pty {
            let mut cfg: PtyBackendConfig = serde_json::from_value(backend_config_value.clone())
                .map_err(|e| {
                    Error::bad_request(format!(
                        "backend_config 格式无效: {e}（保存 Agent 时请包含 preset，例如 codex-exec）"
                    ))
                })?;
            let is_builtin = if exists > 0 {
                sqlx::query_scalar::<_, i64>("SELECT is_builtin FROM friends WHERE id = ?")
                    .bind(&id)
                    .fetch_one(self.pool())
                    .await?
                    != 0
            } else {
                false
            };
            crate::friend_cli::normalize_pty_config(&mut cfg, is_builtin);
            if backend_config_value
                .get("clear_cli_api_key")
                .and_then(|v| v.as_bool())
                .unwrap_or(false)
            {
                crate::friend_cli::clear_pty_cli_api_key(&self.vault, &mut cfg)?;
            }
            crate::friend_cli::persist_pty_cli_api_key(&self.vault, &id, &mut cfg)?;
            backend_config_value = serde_json::to_value(&cfg)?;
            if let Some(obj) = backend_config_value.as_object_mut() {
                obj.remove("clear_cli_api_key");
                obj.remove("cli_api_key");
            }
            let has_preset = cfg
                .preset
                .as_ref()
                .map(|s| !s.trim().is_empty())
                .unwrap_or(false);
            if !has_preset && !is_builtin {
                return Err(crate::Error::bad_request(
                    "Agent 好友必须选择 CLI 预设（如 Codex CLI、Claude、Worker Bee）",
                ));
            }
            tracing::info!(
                friend_id = %id,
                preset = ?cfg.preset,
                cmd = %cfg.cmd,
                "upsert_friend pty config"
            );
            let cwd_empty = cfg
                .cwd
                .as_ref()
                .map(|s| s.trim().is_empty())
                .unwrap_or(true);
            if cwd_empty && !crate::friend_cli::pty_execution_is_relay(&cfg) {
                let path = cli_workspace::ensure_for_friend(&id)?;
                cfg.cwd = Some(path);
                backend_config_value = serde_json::to_value(&cfg)?;
            }
        }
        let backend_config = serde_json::to_string(&backend_config_value)?;
        let kind = req.backend_kind.as_str();
        let now = Utc::now().to_rfc3339();

        if exists == 0 {
            sqlx::query(
                "INSERT INTO friends (id, name, avatar, system_prompt, personality, focus_tags, backend_kind, backend_config, judge_provider_ref, enabled, is_builtin, tenant_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?)",
            )
            .bind(&id)
            .bind(&req.name)
            .bind(&req.avatar)
            .bind(&req.system_prompt)
            .bind(&req.personality)
            .bind(&focus_tags)
            .bind(kind)
            .bind(&backend_config)
            .bind(&req.judge_provider_ref)
            .bind(req.enabled)
            .bind(self.tenant_id())
            .bind(&now)
            .execute(self.pool())
            .await?;
        } else {
            sqlx::query(
                "UPDATE friends SET name=?, avatar=?, system_prompt=?, personality=?, focus_tags=?, backend_kind=?, backend_config=?, judge_provider_ref=?, enabled=? WHERE id=?",
            )
            .bind(&req.name)
            .bind(&req.avatar)
            .bind(&req.system_prompt)
            .bind(&req.personality)
            .bind(&focus_tags)
            .bind(kind)
            .bind(&backend_config)
            .bind(&req.judge_provider_ref)
            .bind(req.enabled)
            .bind(&id)
            .execute(self.pool())
            .await?;
        }

        if req.backend_kind != BackendKind::Human {
            self.ensure_friend_workspaces(&id).await?;
        }

        self.get_friend(&id)
            .await?
            .ok_or_else(|| Error::not_found("friend after upsert"))
    }

    pub async fn delete_friend(&self, id: &str) -> Result<()> {
        sqlx::query("DELETE FROM friends WHERE id = ? AND is_builtin = 0")
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn patch_friend_cli_session_id(
        &self,
        friend_id: &str,
        session_id: Option<String>,
    ) -> Result<()> {
        let friend = self
            .get_friend(friend_id)
            .await?
            .ok_or_else(|| Error::not_found(format!("friend {friend_id}")))?;
        let sid = session_id.filter(|s| !s.trim().is_empty());
        let cfg: PtyBackendConfig =
            serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
        let tool = crate::cli_tool::tool_for_preset(cfg.preset.as_deref());
        if let (Some(tool), Some(ws)) = (
            tool,
            self.get_active_workspace(friend_id)
                .await?
                .or(self.default_workspace_for_friend(friend_id).await?),
        ) {
            let _ = self
                .patch_cli_session_native_id(&ws.id, tool, sid.clone())
                .await;
        }
        let mut cfg: PtyBackendConfig = cfg;
        cfg.cli_session_id = sid;
        let backend_config = serde_json::to_string(&serde_json::to_value(&cfg)?)?;
        sqlx::query("UPDATE friends SET backend_config = ? WHERE id = ?")
            .bind(&backend_config)
            .bind(friend_id)
            .execute(self.pool())
            .await?;
        Ok(())
    }
}
