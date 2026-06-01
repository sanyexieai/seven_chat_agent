use chrono::Utc;
use uuid::Uuid;

use crate::cli_tool::{self, TOOL_CODEX};
use crate::cli_transcript::{
    self, scan_claude_sessions, scan_codex_as_external, scan_cursor_agent_transcripts,
    ExternalCliSessionMeta,
};
use crate::domain::{CliSession, PtyBackendConfig, Workspace};
use crate::memory_tier::{self, TIER_RAW};
use crate::store::memory::NewMemory;
use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

#[derive(Debug, sqlx::FromRow)]
struct CliSessionRow {
    id: String,
    tenant_id: String,
    workspace_id: String,
    tool: String,
    native_session_id: Option<String>,
    label: Option<String>,
    source_path: Option<String>,
    is_active: i64,
    last_used_at: Option<String>,
    created_at: String,
    updated_at: String,
}

impl CliSessionRow {
    fn into_session(self) -> CliSession {
        CliSession {
            id: self.id,
            tenant_id: self.tenant_id,
            workspace_id: self.workspace_id,
            tool: self.tool,
            native_session_id: self.native_session_id,
            label: self.label,
            source_path: self.source_path,
            is_active: self.is_active != 0,
            last_used_at: self.last_used_at.as_deref().map(parse_dt),
            created_at: parse_dt(&self.created_at),
            updated_at: parse_dt(&self.updated_at),
        }
    }
}

const SESSION_SELECT: &str =
    "id, tenant_id, workspace_id, tool, native_session_id, label, source_path, is_active, last_used_at, created_at, updated_at";

#[derive(Debug, Clone, serde::Serialize)]
pub struct CliImportReport {
    pub scanned: usize,
    pub matched: usize,
    pub imported: usize,
    pub memories_created: usize,
}

impl SqliteStore {
    pub async fn list_cli_sessions(&self, workspace_id: &str) -> Result<Vec<CliSession>> {
        let rows = sqlx::query_as::<_, CliSessionRow>(&format!(
            "SELECT {SESSION_SELECT} FROM cli_sessions WHERE tenant_id = ? AND workspace_id = ? ORDER BY is_active DESC, last_used_at DESC, updated_at DESC"
        ))
        .bind(self.tenant_id())
        .bind(workspace_id)
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(|r| r.into_session()).collect())
    }

    pub async fn get_active_cli_session(
        &self,
        workspace_id: &str,
        tool: &str,
    ) -> Result<Option<CliSession>> {
        let row = sqlx::query_as::<_, CliSessionRow>(&format!(
            "SELECT {SESSION_SELECT} FROM cli_sessions WHERE tenant_id = ? AND workspace_id = ? AND tool = ? AND is_active = 1 LIMIT 1"
        ))
        .bind(self.tenant_id())
        .bind(workspace_id)
        .bind(tool)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(|r| r.into_session()))
    }

    pub async fn set_active_cli_session(
        &self,
        workspace_id: &str,
        session_id: &str,
    ) -> Result<()> {
        let sess = self
            .get_cli_session(session_id)
            .await?
            .ok_or_else(|| Error::not_found("cli_session"))?;
        if sess.workspace_id != workspace_id {
            return Err(Error::bad_request("会话不属于该工作区"));
        }
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "UPDATE cli_sessions SET is_active = 0, updated_at = ? WHERE workspace_id = ? AND tool = ?",
        )
        .bind(&now)
        .bind(workspace_id)
        .bind(&sess.tool)
        .execute(self.pool())
        .await?;
        sqlx::query(
            "UPDATE cli_sessions SET is_active = 1, last_used_at = ?, updated_at = ? WHERE id = ?",
        )
        .bind(&now)
        .bind(&now)
        .bind(session_id)
        .execute(self.pool())
        .await?;
        self.sync_workspace_legacy_session(&sess).await?;
        Ok(())
    }

    pub async fn get_cli_session(&self, id: &str) -> Result<Option<CliSession>> {
        let row = sqlx::query_as::<_, CliSessionRow>(&format!(
            "SELECT {SESSION_SELECT} FROM cli_sessions WHERE id = ? AND tenant_id = ?"
        ))
        .bind(id)
        .bind(self.tenant_id())
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(|r| r.into_session()))
    }

    pub async fn upsert_cli_session(
        &self,
        workspace_id: &str,
        tool: &str,
        native_session_id: Option<String>,
        label: Option<String>,
        source_path: Option<String>,
        set_active: bool,
    ) -> Result<CliSession> {
        let native = native_session_id.filter(|s| !s.trim().is_empty());
        let src = source_path.filter(|s| !s.trim().is_empty());
        if let Some(ref path) = src {
            if let Some(existing) = sqlx::query_as::<_, CliSessionRow>(&format!(
                "SELECT {SESSION_SELECT} FROM cli_sessions WHERE source_path = ? AND tenant_id = ? LIMIT 1"
            ))
            .bind(path)
            .bind(self.tenant_id())
            .fetch_optional(self.pool())
            .await?
            {
                let id = existing.id.clone();
                let now = Utc::now().to_rfc3339();
                sqlx::query(
                    r#"UPDATE cli_sessions SET native_session_id = COALESCE(?, native_session_id),
                       label = COALESCE(?, label), last_used_at = ?, updated_at = ? WHERE id = ?"#,
                )
                .bind(&native)
                .bind(label.as_deref())
                .bind(&now)
                .bind(&now)
                .bind(&id)
                .execute(self.pool())
                .await?;
                if set_active {
                    self.set_active_cli_session(workspace_id, &id).await?;
                }
                return self
                    .get_cli_session(&id)
                    .await?
                    .ok_or_else(|| Error::not_found("cli_session"));
            }
        }
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let active = if set_active { 1 } else { 0 };
        if set_active {
            sqlx::query(
                "UPDATE cli_sessions SET is_active = 0, updated_at = ? WHERE workspace_id = ? AND tool = ?",
            )
            .bind(&now)
            .bind(workspace_id)
            .bind(tool)
            .execute(self.pool())
            .await?;
        }
        sqlx::query(
            r#"INSERT INTO cli_sessions (id, tenant_id, workspace_id, tool, native_session_id, label, source_path, is_active, last_used_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"#,
        )
        .bind(&id)
        .bind(self.tenant_id())
        .bind(workspace_id)
        .bind(tool)
        .bind(&native)
        .bind(label.as_deref())
        .bind(src.as_deref())
        .bind(active)
        .bind(&now)
        .bind(&now)
        .bind(&now)
        .execute(self.pool())
        .await?;
        let sess = self
            .get_cli_session(&id)
            .await?
            .ok_or_else(|| Error::not_found("cli_session after insert"))?;
        if set_active {
            self.sync_workspace_legacy_session(&sess).await?;
        }
        Ok(sess)
    }

    pub async fn patch_cli_session_native_id(
        &self,
        workspace_id: &str,
        tool: &str,
        native_session_id: Option<String>,
    ) -> Result<()> {
        let sid = native_session_id.filter(|s| !s.trim().is_empty());
        if let Some(active) = self.get_active_cli_session(workspace_id, tool).await? {
            let now = Utc::now().to_rfc3339();
            sqlx::query(
                "UPDATE cli_sessions SET native_session_id = ?, last_used_at = ?, updated_at = ? WHERE id = ?",
            )
            .bind(&sid)
            .bind(&now)
            .bind(&now)
            .bind(&active.id)
            .execute(self.pool())
            .await?;
            let sess = self
                .get_cli_session(&active.id)
                .await?
                .ok_or_else(|| Error::not_found("cli_session"))?;
            self.sync_workspace_legacy_session(&sess).await?;
            return Ok(());
        }
        if sid.is_some() {
            self.upsert_cli_session(workspace_id, tool, sid, None, None, true)
                .await?;
        }
        Ok(())
    }

    async fn sync_workspace_legacy_session(&self, sess: &CliSession) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            r#"UPDATE workspaces SET cli_session_id = ?, updated_at = ? WHERE id = ? AND tenant_id = ?"#,
        )
        .bind(&sess.native_session_id)
        .bind(&now)
        .bind(&sess.workspace_id)
        .bind(self.tenant_id())
        .execute(self.pool())
        .await?;
        let ws = self
            .get_workspace(&sess.workspace_id)
            .await?
            .ok_or_else(|| Error::not_found("workspace"))?;
        let friend = self
            .get_friend(&ws.owner_friend_id)
            .await?
            .ok_or_else(|| Error::not_found("friend"))?;
        let mut cfg: PtyBackendConfig =
            serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
        cfg.cli_session_id = sess.native_session_id.clone();
        let backend_config = serde_json::to_string(&serde_json::to_value(&cfg)?)?;
        sqlx::query("UPDATE friends SET backend_config = ? WHERE id = ?")
            .bind(&backend_config)
            .bind(&ws.owner_friend_id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    /// 将 workspaces 表 legacy `cli_session_id` 迁入 `cli_sessions`。
    pub async fn migrate_legacy_workspace_cli_sessions(&self) -> Result<()> {
        let rows: Vec<(String, Option<String>, Option<String>, String)> = sqlx::query_as(
            r#"SELECT w.id, w.cli_session_id, w.cli_session_mode, w.owner_friend_id
               FROM workspaces w
               WHERE w.cli_session_id IS NOT NULL AND trim(w.cli_session_id) != ''"#,
        )
        .fetch_all(self.pool())
        .await?;
        for (ws_id, sid, _mode, owner) in rows {
            let count: i64 = sqlx::query_scalar(
                "SELECT COUNT(*) FROM cli_sessions WHERE workspace_id = ?",
            )
            .bind(&ws_id)
            .fetch_one(self.pool())
            .await?;
            if count > 0 {
                continue;
            }
            let friend = match self.get_friend(&owner).await {
                Ok(Some(f)) => f,
                _ => continue,
            };
            let cfg: PtyBackendConfig =
                serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
            let tool = cli_tool::tool_for_preset(cfg.preset.as_deref()).unwrap_or(TOOL_CODEX);
            let _ = self
                .upsert_cli_session(&ws_id, tool, sid, Some("默认迁移".into()), None, true)
                .await;
        }
        Ok(())
    }

    pub async fn import_codex_sessions_for_workspace(
        &self,
        workspace_id: &str,
        ingest_memories: bool,
    ) -> Result<CliImportReport> {
        let home = cli_transcript::codex_home();
        let metas = scan_codex_as_external(&home);
        self.import_external_sessions_for_workspace(workspace_id, metas, ingest_memories)
            .await
    }

    pub async fn import_claude_sessions_for_workspace(
        &self,
        workspace_id: &str,
        ingest_memories: bool,
    ) -> Result<CliImportReport> {
        let home = cli_transcript::claude_config_dir();
        let metas = scan_claude_sessions(&home);
        self.import_external_sessions_for_workspace(workspace_id, metas, ingest_memories)
            .await
    }

    pub async fn import_cursor_sessions_for_workspace(
        &self,
        workspace_id: &str,
        ingest_memories: bool,
    ) -> Result<CliImportReport> {
        let home = cli_transcript::cursor_home();
        let metas = scan_cursor_agent_transcripts(&home);
        self.import_external_sessions_for_workspace(workspace_id, metas, ingest_memories)
            .await
    }

    /// 按工作区路径匹配，批量导入外部 CLI 会话元数据。
    pub async fn import_external_sessions_for_workspace(
        &self,
        workspace_id: &str,
        metas: Vec<ExternalCliSessionMeta>,
        ingest_memories: bool,
    ) -> Result<CliImportReport> {
        let ws = self
            .get_workspace(workspace_id)
            .await?
            .ok_or_else(|| Error::not_found("workspace"))?;
        let friend = self
            .get_friend(&ws.owner_friend_id)
            .await?
            .ok_or_else(|| Error::not_found("friend"))?;
        let ws_path = std::path::Path::new(&ws.path);
        let mut report = CliImportReport {
            scanned: metas.len(),
            matched: 0,
            imported: 0,
            memories_created: 0,
        };
        let mut first_new: Option<String> = None;
        for r in metas {
            if !cli_transcript::session_matches_workspace(&r, ws_path) {
                continue;
            }
            report.matched += 1;
            let label = r
                .first_ask
                .clone()
                .or_else(|| r.cwd.clone())
                .map(|s| crate::assistant_accumulation::truncate_chars(&s, 80));
            let sess = self
                .upsert_cli_session(
                    workspace_id,
                    r.tool,
                    Some(r.native_session_id.clone()),
                    label.clone(),
                    r.source_path.to_str().map(String::from),
                    false,
                )
                .await?;
            if first_new.is_none() {
                first_new = Some(sess.id.clone());
            }
            report.imported += 1;

            if ingest_memories {
                if let Some(ref ask) = r.first_ask {
                    let marker = format!(
                        "[CLI导入/{}] id={}",
                        r.tool, r.native_session_id
                    );
                    let dup: i64 = sqlx::query_scalar(
                        "SELECT COUNT(*) FROM memories WHERE tenant_id = ? AND owner_friend_id = ? AND content LIKE ?",
                    )
                    .bind(self.tenant_id())
                    .bind(&friend.id)
                    .bind(format!("{marker}%"))
                    .fetch_one(self.pool())
                    .await?;
                    if dup == 0 {
                        let content = format!(
                            "{marker}\n工作区: {}\n路径: {}\n摘要: {}",
                            ws.name,
                            r.source_path.display(),
                            ask
                        );
                        let _ = self
                            .insert_memory(NewMemory {
                                owner_friend_id: friend.id.clone(),
                                kind: crate::assistant_accumulation::MEMORY_KIND_MEMO.to_string(),
                                content,
                                source_message_id: None,
                                weight: 0.2,
                                pinned: false,
                                tier: TIER_RAW.to_string(),
                                scope: memory_tier::SCOPE_WORKSPACE.to_string(),
                                scope_ref: Some(workspace_id.to_string()),
                                importance: 0,
                                status: memory_tier::STATUS_ACTIVE.to_string(),
                                title: label.clone(),
                                summary: None,
                                expires_at: None,
                                workspace_id: Some(workspace_id.to_string()),
                            })
                            .await;
                        report.memories_created += 1;
                    }
                }
            }
        }
        if report.imported > 0 {
            if let Some(sid) = first_new {
                let _ = self.set_active_cli_session(workspace_id, &sid).await;
            }
        }
        Ok(report)
    }
}

/// 合并工作区路径 + 当前工具的 active CLI 会话到 Pty 配置。
pub fn apply_workspace_and_cli_session(
    cfg: &mut PtyBackendConfig,
    ws: &Workspace,
    cli_sess: Option<&CliSession>,
) {
    crate::store::workspace::apply_workspace_to_pty(cfg, ws);
    if let Some(sess) = cli_sess {
        if sess
            .native_session_id
            .as_ref()
            .is_some_and(|s| !s.trim().is_empty())
        {
            cfg.cli_session_id = sess.native_session_id.clone();
        }
    }
}
