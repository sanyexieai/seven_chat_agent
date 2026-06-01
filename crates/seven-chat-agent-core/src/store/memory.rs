use std::collections::HashSet;

use chrono::Utc;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::domain::AssistantGlobalSettings;
use crate::memory_embedding::{cosine_similarity, decode_embedding, encode_embedding};
use crate::memory_tier::{
    self, RecallContext, STATUS_ACTIVE, STATUS_ARCHIVED, TIER_CURATED, TIER_RAW,
};
use crate::provider::ProviderRegistry;
use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

const MEMORY_SELECT: &str = "id, owner_friend_id, kind, content, source_message_id, weight, pinned, last_used_at, decay_score, created_at, tier, scope, scope_ref, importance, status, title, summary, tenant_id, expires_at";

/// 可选向量召回（需 embedding API）。
pub struct RecallVectorOpts<'a> {
    pub providers: &'a ProviderRegistry,
    pub settings: &'a AssistantGlobalSettings,
    pub assistant_id: &'a str,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Memory {
    pub id: String,
    pub owner_friend_id: String,
    pub kind: String,
    pub content: String,
    pub source_message_id: Option<String>,
    pub weight: f64,
    pub pinned: bool,
    pub last_used_at: Option<chrono::DateTime<chrono::Utc>>,
    pub decay_score: f64,
    pub created_at: chrono::DateTime<chrono::Utc>,
    pub tier: String,
    pub scope: String,
    pub scope_ref: Option<String>,
    pub importance: i32,
    pub status: String,
    pub title: Option<String>,
    pub summary: Option<String>,
    pub tenant_id: String,
    pub expires_at: Option<chrono::DateTime<chrono::Utc>>,
}

#[derive(Debug, sqlx::FromRow)]
struct MemoryRow {
    id: String,
    owner_friend_id: String,
    kind: String,
    content: String,
    source_message_id: Option<String>,
    weight: f64,
    pinned: i64,
    last_used_at: Option<String>,
    decay_score: f64,
    created_at: String,
    tier: String,
    scope: String,
    scope_ref: Option<String>,
    importance: i32,
    status: String,
    title: Option<String>,
    summary: Option<String>,
    tenant_id: String,
    expires_at: Option<String>,
}

impl From<MemoryRow> for Memory {
    fn from(r: MemoryRow) -> Self {
        Memory {
            id: r.id,
            owner_friend_id: r.owner_friend_id,
            kind: r.kind,
            content: r.content,
            source_message_id: r.source_message_id,
            weight: r.weight,
            pinned: r.pinned != 0,
            last_used_at: r.last_used_at.as_deref().map(parse_dt),
            decay_score: r.decay_score,
            created_at: parse_dt(&r.created_at),
            tier: r.tier,
            scope: r.scope,
            scope_ref: r.scope_ref,
            importance: r.importance,
            status: r.status,
            title: r.title,
            summary: r.summary,
            tenant_id: r.tenant_id,
            expires_at: r.expires_at.as_deref().map(parse_dt),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryStats {
    pub total: i64,
    pub curated_active: i64,
    pub raw_active: i64,
    pub raw_archived: i64,
    pub memo_count: i64,
    pub knowledge_count: i64,
    pub pinned_count: i64,
    pub observe_count: i64,
    pub assist_count: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NewMemory {
    pub owner_friend_id: String,
    pub kind: String,
    pub content: String,
    pub source_message_id: Option<String>,
    pub weight: f64,
    #[serde(default)]
    pub pinned: bool,
    #[serde(default = "default_tier_curated")]
    pub tier: String,
    #[serde(default = "default_scope_global")]
    pub scope: String,
    pub scope_ref: Option<String>,
    #[serde(default = "default_importance")]
    pub importance: i32,
    #[serde(default = "default_status_active")]
    pub status: String,
    pub title: Option<String>,
    pub summary: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expires_at: Option<chrono::DateTime<chrono::Utc>>,
}

fn default_tier_curated() -> String {
    TIER_CURATED.to_string()
}
fn default_scope_global() -> String {
    memory_tier::SCOPE_GLOBAL.to_string()
}
fn default_importance() -> i32 {
    1
}
fn default_status_active() -> String {
    STATUS_ACTIVE.to_string()
}

#[derive(Debug, Clone, Default)]
pub struct ListMemoryFilter {
    pub tier: Option<String>,
    pub status: Option<String>,
    pub scope: Option<String>,
    pub category: Option<String>,
}

impl SqliteStore {
    pub fn ephemeral_expires_at(&self, settings: &AssistantGlobalSettings) -> chrono::DateTime<chrono::Utc> {
        let hours = settings.ephemeral_ttl_hours.max(1);
        Utc::now() + chrono::Duration::hours(hours as i64)
    }

    pub async fn insert_memory(&self, m: NewMemory) -> Result<Memory> {
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let summary = m
            .summary
            .clone()
            .or_else(|| {
                if m.tier == TIER_CURATED {
                    Some(memory_tier::make_summary(&m.content, 240))
                } else {
                    None
                }
            });
        let mut scope_ref = m.scope_ref.clone();
        if m.scope == memory_tier::SCOPE_USER && scope_ref.is_none() {
            scope_ref = Some(self.tenant_id().to_string());
        }
        let expires_at = if let Some(t) = m.expires_at {
            Some(t)
        } else if m.scope == memory_tier::SCOPE_EPHEMERAL {
            let settings = self.get_assistant_global_settings().await?;
            Some(self.ephemeral_expires_at(&settings))
        } else {
            None
        };
        let expires_at_str = expires_at.map(|t| t.to_rfc3339());
        sqlx::query(
            r#"INSERT INTO memories (
                id, owner_friend_id, kind, content, source_message_id, weight, pinned,
                decay_score, created_at, tier, scope, scope_ref, importance, status,
                title, summary, tenant_id, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"#,
        )
        .bind(&id)
        .bind(&m.owner_friend_id)
        .bind(&m.kind)
        .bind(&m.content)
        .bind(&m.source_message_id)
        .bind(m.weight)
        .bind(if m.pinned { 1 } else { 0 })
        .bind(&now)
        .bind(&m.tier)
        .bind(&m.scope)
        .bind(&scope_ref)
        .bind(m.importance)
        .bind(&m.status)
        .bind(&m.title)
        .bind(&summary)
        .bind(self.tenant_id())
        .bind(&expires_at_str)
        .execute(self.pool())
        .await?;
        self.get_memory(&id)
            .await?
            .ok_or_else(|| Error::not_found("memory after insert"))
    }

    pub async fn get_memory(&self, id: &str) -> Result<Option<Memory>> {
        let sql = format!(
            "SELECT {MEMORY_SELECT} FROM memories WHERE id = ? AND tenant_id = ?"
        );
        let row: Option<MemoryRow> = sqlx::query_as::<_, MemoryRow>(&sql)
            .bind(id)
            .bind(self.tenant_id())
            .fetch_optional(self.pool())
            .await?;
        Ok(row.map(Memory::from))
    }

    pub async fn list_memories_by_category(
        &self,
        owner: &str,
        category: Option<&str>,
        limit: i64,
    ) -> Result<Vec<Memory>> {
        self.list_memories_filtered(owner, ListMemoryFilter {
            category: category.map(String::from),
            ..Default::default()
        }, limit)
            .await
    }

    pub async fn list_memories(
        &self,
        owner: &str,
        kind: Option<&str>,
        limit: i64,
    ) -> Result<Vec<Memory>> {
        let rows: Vec<MemoryRow> = if let Some(k) = kind {
            let sql = format!(
                "SELECT {MEMORY_SELECT} FROM memories WHERE tenant_id = ? AND owner_friend_id = ? AND kind = ? ORDER BY pinned DESC, importance DESC, weight DESC, created_at DESC LIMIT ?"
            );
            sqlx::query_as::<_, MemoryRow>(&sql)
                .bind(self.tenant_id())
                .bind(owner)
                .bind(k)
                .bind(limit)
                .fetch_all(self.pool())
                .await?
        } else {
            let sql = format!(
                "SELECT {MEMORY_SELECT} FROM memories WHERE tenant_id = ? AND owner_friend_id = ? ORDER BY pinned DESC, importance DESC, weight DESC, created_at DESC LIMIT ?"
            );
            sqlx::query_as::<_, MemoryRow>(&sql)
                .bind(self.tenant_id())
                .bind(owner)
                .bind(limit)
                .fetch_all(self.pool())
                .await?
        };
        Ok(rows.into_iter().map(Memory::from).collect())
    }

    pub async fn list_memories_filtered(
        &self,
        owner: &str,
        filter: ListMemoryFilter,
        limit: i64,
    ) -> Result<Vec<Memory>> {
        let mut sql = format!(
            "SELECT {MEMORY_SELECT} FROM memories WHERE tenant_id = ? AND owner_friend_id = ?"
        );
        if filter.tier.as_deref().is_some() {
            sql.push_str(" AND tier = ?");
        }
        if filter.status.as_deref().is_some() {
            sql.push_str(" AND status = ?");
        }
        if filter.scope.as_deref().is_some() {
            sql.push_str(" AND scope = ?");
        }
        sql.push_str(" ORDER BY pinned DESC, importance DESC, weight DESC, created_at DESC LIMIT ?");

        let mut q = sqlx::query_as::<_, MemoryRow>(&sql)
            .bind(self.tenant_id())
            .bind(owner);
        if let Some(t) = &filter.tier {
            q = q.bind(t);
        }
        if let Some(s) = &filter.status {
            q = q.bind(s);
        }
        if let Some(sc) = &filter.scope {
            q = q.bind(sc);
        }
        q = q.bind(limit);
        let rows = q.fetch_all(self.pool()).await?;
        let mut out: Vec<Memory> = rows.into_iter().map(Memory::from).collect();
        if let Some(cat) = filter.category.as_deref() {
            out = match cat {
                "memo" => out
                    .into_iter()
                    .filter(|m| crate::assistant_accumulation::is_memo_kind(&m.kind))
                    .collect(),
                "knowledge" => out
                    .into_iter()
                    .filter(|m| crate::assistant_accumulation::is_knowledge_kind(&m.kind))
                    .collect(),
                _ => out,
            };
        }
        Ok(out)
    }

    /// 仅 **整理层 + 活跃** 且作用域匹配的记忆进入提示词。
    pub async fn recall_memories_for_turn(
        &self,
        owner: &str,
        query: &str,
        limit: i64,
        touch_used: bool,
        ctx: &RecallContext,
    ) -> Result<Vec<Memory>> {
        self.recall_memories_for_turn_with_vector(owner, query, limit, touch_used, ctx, None)
            .await
    }

    pub async fn recall_memories_for_turn_with_vector(
        &self,
        owner: &str,
        query: &str,
        limit: i64,
        touch_used: bool,
        ctx: &RecallContext,
        vector: Option<RecallVectorOpts<'_>>,
    ) -> Result<Vec<Memory>> {
        let limit = limit.clamp(1, 32);
        let pool = self.list_recall_candidates(owner, ctx, limit * 8).await?;
        let mut seen = HashSet::new();
        let mut out = Vec::new();

        for m in pool.iter().filter(|m| m.pinned) {
            push_unique(&mut out, &mut seen, m.clone(), limit);
        }
        for m in self
            .search_memories_curated(owner, query, ctx, limit)
            .await?
        {
            push_unique(&mut out, &mut seen, m, limit);
        }
        if let Some(vopts) = vector {
            if vopts.settings.embedding_enabled {
                for m in self
                    .search_memories_vector(
                        owner,
                        query,
                        ctx,
                        limit,
                        vopts.providers,
                        vopts.settings,
                        vopts.assistant_id,
                    )
                    .await
                    .unwrap_or_default()
                {
                    push_unique(&mut out, &mut seen, m, limit);
                }
            }
        }
        for m in pool {
            push_unique(&mut out, &mut seen, m, limit);
        }

        if touch_used {
            for m in &out {
                let _ = self.touch_memory(&m.id).await;
            }
        }
        Ok(out)
    }

    async fn list_recall_candidates(
        &self,
        owner: &str,
        ctx: &RecallContext,
        limit: i64,
    ) -> Result<Vec<Memory>> {
        let sql = format!(
            r#"
            SELECT {MEMORY_SELECT} FROM memories
            WHERE tenant_id = ?
              AND owner_friend_id = ?
              AND tier = ?
              AND status = ?
              AND (expires_at IS NULL OR expires_at > ?)
              AND (
                scope = 'global'
                OR (scope = 'user' AND (scope_ref IS NULL OR scope_ref = ?))
                OR (scope = 'friend' AND (scope_ref IS NULL OR scope_ref = ?))
                OR (scope = 'conversation' AND scope_ref = ?)
                OR (scope = 'ephemeral' AND scope_ref = ?)
              )
            ORDER BY importance DESC, pinned DESC, weight DESC, created_at DESC
            LIMIT ?
            "#,
        );
        let conv = ctx.conversation_id.as_deref().unwrap_or("");
        let friend = ctx.friend_id.as_deref().unwrap_or("");
        let now = Utc::now().to_rfc3339();
        let rows: Vec<MemoryRow> = sqlx::query_as(&sql)
            .bind(self.tenant_id())
            .bind(owner)
            .bind(TIER_CURATED)
            .bind(STATUS_ACTIVE)
            .bind(&now)
            .bind(self.tenant_id())
            .bind(friend)
            .bind(conv)
            .bind(conv)
            .bind(limit)
            .fetch_all(self.pool())
            .await?;
        Ok(rows.into_iter().map(Memory::from).collect())
    }

    async fn search_memories_curated(
        &self,
        owner: &str,
        query: &str,
        ctx: &RecallContext,
        limit: i64,
    ) -> Result<Vec<Memory>> {
        let q = sanitize_fts(query);
        if q.is_empty() {
            return Ok(vec![]);
        }
        let conv = ctx.conversation_id.as_deref().unwrap_or("");
        let friend = ctx.friend_id.as_deref().unwrap_or("");
        let sql = format!(
            r#"
            SELECT m.id, m.owner_friend_id, m.kind, m.content, m.source_message_id, m.weight, m.pinned,
                   m.last_used_at, m.decay_score, m.created_at, m.tier, m.scope, m.scope_ref, m.importance,
                   m.status, m.title, m.summary, m.tenant_id, m.expires_at
            FROM memories_fts f
            JOIN memories m ON m.rowid = f.rowid
            WHERE memories_fts MATCH ?
              AND m.tenant_id = ?
              AND m.owner_friend_id = ?
              AND m.tier = ?
              AND m.status = ?
              AND (m.expires_at IS NULL OR m.expires_at > ?)
              AND (
                m.scope = 'global'
                OR (m.scope = 'user' AND (m.scope_ref IS NULL OR m.scope_ref = ?))
                OR (m.scope = 'friend' AND (m.scope_ref IS NULL OR m.scope_ref = ?))
                OR (m.scope = 'conversation' AND m.scope_ref = ?)
                OR (m.scope = 'ephemeral' AND m.scope_ref = ?)
              )
            ORDER BY m.importance DESC, m.pinned DESC, m.weight DESC, m.created_at DESC
            LIMIT ?
            "#,
        );
        let now = Utc::now().to_rfc3339();
        let rows: Vec<MemoryRow> = sqlx::query_as(&sql)
            .bind(&q)
            .bind(self.tenant_id())
            .bind(owner)
            .bind(TIER_CURATED)
            .bind(STATUS_ACTIVE)
            .bind(&now)
            .bind(self.tenant_id())
            .bind(friend)
            .bind(conv)
            .bind(conv)
            .bind(limit)
            .fetch_all(self.pool())
            .await?;
        Ok(rows.into_iter().map(Memory::from).collect())
    }

    pub async fn memory_stats(&self, owner: &str) -> Result<MemoryStats> {
        let row: (i64, i64, i64, i64, i64, i64) = sqlx::query_as(
            r#"
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN tier = 'curated' AND status = 'active' THEN 1 ELSE 0 END),
                SUM(CASE WHEN tier = 'raw' AND status = 'active' THEN 1 ELSE 0 END),
                SUM(CASE WHEN tier = 'raw' AND status = 'archived' THEN 1 ELSE 0 END),
                SUM(CASE WHEN pinned = 1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN content LIKE '[默认观察/%' THEN 1 ELSE 0 END)
            FROM memories WHERE tenant_id = ? AND owner_friend_id = ?
            "#,
        )
        .bind(self.tenant_id())
        .bind(owner)
        .fetch_one(self.pool())
        .await?;
        let assist_count = sqlx::query_scalar::<_, i64>(
            "SELECT COUNT(*) FROM memories WHERE tenant_id = ? AND owner_friend_id = ? AND content LIKE '[协助记录]%'",
        )
        .bind(self.tenant_id())
        .bind(owner)
        .fetch_one(self.pool())
        .await?;
        let memo_count = sqlx::query_scalar::<_, i64>(
            r#"
            SELECT COUNT(*) FROM memories WHERE tenant_id = ? AND owner_friend_id = ? AND tier = 'raw' AND status = 'active'
            "#,
        )
        .bind(self.tenant_id())
        .bind(owner)
        .fetch_one(self.pool())
        .await?;
        let knowledge_count = sqlx::query_scalar::<_, i64>(
            r#"
            SELECT COUNT(*) FROM memories
            WHERE tenant_id = ? AND owner_friend_id = ? AND tier = 'curated' AND status = 'active'
              AND kind IN ('knowledge', 'fact', 'preference', 'project', 'relation', 'lesson')
            "#,
        )
        .bind(self.tenant_id())
        .bind(owner)
        .fetch_one(self.pool())
        .await?;
        Ok(MemoryStats {
            total: row.0,
            curated_active: row.1,
            raw_active: row.2,
            raw_archived: row.3,
            pinned_count: row.4,
            observe_count: row.5,
            assist_count,
            memo_count,
            knowledge_count,
        })
    }

    pub async fn search_memories(
        &self,
        owner: &str,
        query: &str,
        limit: i64,
    ) -> Result<Vec<Memory>> {
        self.search_memories_curated(owner, query, &RecallContext::default(), limit)
            .await
    }

    pub async fn touch_memory(&self, id: &str) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "UPDATE memories SET last_used_at = ?, decay_score = MIN(1.0, decay_score + 0.05) WHERE id = ?",
        )
        .bind(&now)
        .bind(id)
        .execute(self.pool())
        .await?;
        Ok(())
    }

    pub async fn delete_memory(&self, id: &str) -> Result<()> {
        sqlx::query("DELETE FROM memories WHERE id = ? AND tenant_id = ?")
            .bind(id)
            .bind(self.tenant_id())
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn pin_memory(&self, id: &str, pinned: bool) -> Result<()> {
        sqlx::query("UPDATE memories SET pinned = ? WHERE id = ?")
            .bind(if pinned { 1 } else { 0 })
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn update_memory(
        &self,
        id: &str,
        kind: Option<&str>,
        content: Option<&str>,
        weight: Option<f64>,
        pinned: Option<bool>,
        tier: Option<&str>,
        scope: Option<&str>,
        scope_ref: Option<Option<&str>>,
        importance: Option<i32>,
        status: Option<&str>,
        title: Option<Option<&str>>,
        summary: Option<Option<&str>>,
        promote_to_curated: bool,
    ) -> Result<Memory> {
        if let Some(k) = kind {
            sqlx::query("UPDATE memories SET kind = ? WHERE id = ?")
                .bind(k)
                .bind(id)
                .execute(self.pool())
                .await?;
        }
        if let Some(c) = content {
            sqlx::query("UPDATE memories SET content = ? WHERE id = ?")
                .bind(c)
                .bind(id)
                .execute(self.pool())
                .await?;
        }
        if let Some(w) = weight {
            sqlx::query("UPDATE memories SET weight = ? WHERE id = ?")
                .bind(w.clamp(0.0, 1.0))
                .bind(id)
                .execute(self.pool())
                .await?;
        }
        if let Some(p) = pinned {
            sqlx::query("UPDATE memories SET pinned = ? WHERE id = ?")
                .bind(if p { 1 } else { 0 })
                .bind(id)
                .execute(self.pool())
                .await?;
        }
        if let Some(t) = tier {
            sqlx::query("UPDATE memories SET tier = ? WHERE id = ?")
                .bind(t)
                .bind(id)
                .execute(self.pool())
                .await?;
        } else if promote_to_curated {
            sqlx::query("UPDATE memories SET tier = ?, status = ? WHERE id = ?")
                .bind(TIER_CURATED)
                .bind(STATUS_ACTIVE)
                .bind(id)
                .execute(self.pool())
                .await?;
        }
        if let Some(s) = scope {
            sqlx::query("UPDATE memories SET scope = ? WHERE id = ?")
                .bind(s)
                .bind(id)
                .execute(self.pool())
                .await?;
        }
        if let Some(sr) = scope_ref {
            sqlx::query("UPDATE memories SET scope_ref = ? WHERE id = ?")
                .bind(sr)
                .bind(id)
                .execute(self.pool())
                .await?;
        }
        if let Some(i) = importance {
            sqlx::query("UPDATE memories SET importance = ? WHERE id = ?")
                .bind(i)
                .bind(id)
                .execute(self.pool())
                .await?;
        }
        if let Some(st) = status {
            sqlx::query("UPDATE memories SET status = ? WHERE id = ?")
                .bind(st)
                .bind(id)
                .execute(self.pool())
                .await?;
        }
        if let Some(t) = title {
            sqlx::query("UPDATE memories SET title = ? WHERE id = ?")
                .bind(t)
                .bind(id)
                .execute(self.pool())
                .await?;
        }
        if let Some(s) = summary {
            sqlx::query("UPDATE memories SET summary = ? WHERE id = ?")
                .bind(s)
                .bind(id)
                .execute(self.pool())
                .await?;
        }
        self.get_memory(id)
            .await?
            .ok_or_else(|| Error::not_found("memory after update"))
    }

    pub async fn consolidate_memories(&self, owner: &str) -> Result<()> {
        let _ = self.purge_expired_memories(owner).await?;
        let archive_cutoff = (Utc::now() - chrono::Duration::days(3)).to_rfc3339();
        sqlx::query(
            r#"
            UPDATE memories SET status = ?
            WHERE tenant_id = ? AND owner_friend_id = ? AND tier = ? AND status = ? AND pinned = 0
              AND created_at < ?
            "#,
        )
        .bind(STATUS_ARCHIVED)
        .bind(self.tenant_id())
        .bind(owner)
        .bind(TIER_RAW)
        .bind(STATUS_ACTIVE)
        .bind(&archive_cutoff)
        .execute(self.pool())
        .await?;

        sqlx::query(
            "UPDATE memories SET decay_score = decay_score * 0.95 WHERE tenant_id = ? AND owner_friend_id = ? AND tier = ? AND pinned = 0",
        )
        .bind(self.tenant_id())
        .bind(owner)
        .bind(TIER_CURATED)
        .execute(self.pool())
        .await?;
        sqlx::query(
            "DELETE FROM memories WHERE tenant_id = ? AND owner_friend_id = ? AND tier = ? AND pinned = 0 AND decay_score < 0.1 AND importance < 2",
        )
        .bind(self.tenant_id())
        .bind(owner)
        .bind(TIER_CURATED)
        .execute(self.pool())
        .await?;

        let purge_cutoff = (Utc::now() - chrono::Duration::days(30)).to_rfc3339();
        sqlx::query(
            r#"
            DELETE FROM memories
            WHERE tenant_id = ? AND owner_friend_id = ? AND tier = ? AND status = ? AND pinned = 0 AND created_at < ?
            "#,
        )
        .bind(self.tenant_id())
        .bind(owner)
        .bind(TIER_RAW)
        .bind(STATUS_ARCHIVED)
        .bind(&purge_cutoff)
        .execute(self.pool())
        .await?;
        Ok(())
    }

    pub async fn purge_expired_memories(&self, owner: &str) -> Result<u64> {
        let now = Utc::now().to_rfc3339();
        let r = sqlx::query(
            r#"
            DELETE FROM memories
            WHERE tenant_id = ? AND owner_friend_id = ?
              AND expires_at IS NOT NULL AND expires_at <= ?
            "#,
        )
        .bind(self.tenant_id())
        .bind(owner)
        .bind(&now)
        .execute(self.pool())
        .await?;
        Ok(r.rows_affected())
    }

    pub async fn list_curated_for_organize(&self, owner: &str, limit: i64) -> Result<Vec<Memory>> {
        let sql = format!(
            r#"
            SELECT {MEMORY_SELECT} FROM memories
            WHERE tenant_id = ? AND owner_friend_id = ?
              AND tier = ? AND status = ?
            ORDER BY importance DESC, pinned DESC, weight DESC, created_at DESC
            LIMIT ?
            "#,
        );
        let rows: Vec<MemoryRow> = sqlx::query_as(&sql)
            .bind(self.tenant_id())
            .bind(owner)
            .bind(TIER_CURATED)
            .bind(STATUS_ACTIVE)
            .bind(limit.max(2))
            .fetch_all(self.pool())
            .await?;
        Ok(rows.into_iter().map(Memory::from).collect())
    }

    pub async fn list_raw_for_ingest(&self, owner: &str, limit: i64) -> Result<Vec<Memory>> {
        let sql = format!(
            r#"
            SELECT {MEMORY_SELECT} FROM memories
            WHERE tenant_id = ? AND owner_friend_id = ?
              AND tier = ? AND status = ?
            ORDER BY created_at ASC
            LIMIT ?
            "#,
        );
        let rows: Vec<MemoryRow> = sqlx::query_as(&sql)
            .bind(self.tenant_id())
            .bind(owner)
            .bind(TIER_RAW)
            .bind(STATUS_ACTIVE)
            .bind(limit.max(1))
            .fetch_all(self.pool())
            .await?;
        Ok(rows.into_iter().map(Memory::from).collect())
    }

    pub async fn archive_memories_by_ids(&self, ids: &[String]) -> Result<usize> {
        if ids.is_empty() {
            return Ok(0);
        }
        let mut archived = 0usize;
        for id in ids {
            let r = sqlx::query(
                r#"UPDATE memories SET status = ? WHERE id = ? AND tenant_id = ? AND tier = ?"#,
            )
            .bind(STATUS_ARCHIVED)
            .bind(id)
            .bind(self.tenant_id())
            .bind(TIER_RAW)
            .execute(self.pool())
            .await?;
            archived += r.rows_affected() as usize;
        }
        Ok(archived)
    }

    pub async fn set_memory_embedding(&self, id: &str, vec: &[f32]) -> Result<()> {
        let blob = encode_embedding(vec);
        sqlx::query("UPDATE memories SET embedding = ? WHERE id = ? AND tenant_id = ?")
            .bind(blob)
            .bind(id)
            .bind(self.tenant_id())
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn list_curated_missing_embedding(
        &self,
        owner: &str,
        limit: i64,
    ) -> Result<Vec<(String, String)>> {
        let rows: Vec<(String, String)> = sqlx::query_as(
            r#"
            SELECT id, content FROM memories
            WHERE tenant_id = ? AND owner_friend_id = ?
              AND tier = ? AND status = ?
              AND embedding IS NULL
            ORDER BY importance DESC, created_at DESC
            LIMIT ?
            "#,
        )
        .bind(self.tenant_id())
        .bind(owner)
        .bind(TIER_CURATED)
        .bind(STATUS_ACTIVE)
        .bind(limit.max(1))
        .fetch_all(self.pool())
        .await?;
        Ok(rows)
    }

    async fn search_memories_vector(
        &self,
        owner: &str,
        query: &str,
        ctx: &RecallContext,
        limit: i64,
        providers: &ProviderRegistry,
        settings: &AssistantGlobalSettings,
        assistant_id: &str,
    ) -> Result<Vec<Memory>> {
        let q = query.trim();
        if q.len() < 4 {
            return Ok(vec![]);
        }
        let provider_id = if let Some(p) = settings
            .embedding_provider_id
            .as_deref()
            .filter(|s| !s.is_empty())
        {
            p.to_string()
        } else if let Ok((p, _, _)) =
            crate::memory_ingest::resolve_assistant_inference(self, assistant_id).await
        {
            p
        } else {
            "openai".to_string()
        };
        let model = settings
            .embedding_model
            .as_deref()
            .filter(|s| !s.is_empty())
            .unwrap_or("text-embedding-3-small");
        let query_vec = providers
            .embed_text(&provider_id, model, q, None)
            .await?;

        let candidates = self
            .list_recall_candidates(owner, ctx, (limit * 12).max(24))
            .await?;
        let mut scored: Vec<(f32, Memory)> = Vec::new();
        for m in candidates {
            let emb: Option<Vec<u8>> = sqlx::query_scalar(
                "SELECT embedding FROM memories WHERE id = ? AND tenant_id = ?",
            )
            .bind(&m.id)
            .bind(self.tenant_id())
            .fetch_optional(self.pool())
            .await?;
            let Some(blob) = emb else {
                continue;
            };
            let Some(stored) = decode_embedding(&blob) else {
                continue;
            };
            let sim = cosine_similarity(&query_vec, &stored);
            if sim > 0.25 {
                scored.push((sim, m));
            }
        }
        scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
        Ok(scored
            .into_iter()
            .take(limit as usize)
            .map(|(_, m)| m)
            .collect())
    }

    pub async fn observe_recent_duplicate(
        &self,
        owner: &str,
        scope: &str,
        body: &str,
        within_secs: i64,
    ) -> Result<bool> {
        let fp = crate::memory_record_policy::content_fingerprint(body);
        if fp.is_empty() || within_secs <= 0 {
            return Ok(false);
        }
        let since = (Utc::now() - chrono::Duration::seconds(within_secs.max(1))).to_rfc3339();
        let pattern = format!("%[默认观察/{scope}]%");
        let sql = format!(
            "SELECT content FROM memories WHERE tenant_id = ? AND owner_friend_id = ? AND tier = ? AND content LIKE ? AND created_at >= ? ORDER BY created_at DESC LIMIT 8"
        );
        let rows: Vec<(String,)> = sqlx::query_as(&sql)
            .bind(self.tenant_id())
            .bind(owner)
            .bind(TIER_RAW)
            .bind(&pattern)
            .bind(&since)
            .fetch_all(self.pool())
            .await?;
        for (content,) in rows {
            let observed = content
                .lines()
                .find(|l| l.starts_with("内容:"))
                .map(|l| l.trim_start_matches("内容:").trim())
                .unwrap_or("");
            if crate::memory_record_policy::content_fingerprint(observed) == fp
                || crate::memory_record_policy::observe_contents_similar(observed, body)
            {
                return Ok(true);
            }
        }
        Ok(false)
    }
}

fn push_unique(out: &mut Vec<Memory>, seen: &mut HashSet<String>, m: Memory, limit: i64) {
    if out.len() as i64 >= limit {
        return;
    }
    if seen.insert(m.id.clone()) {
        out.push(m);
    }
}

fn sanitize_fts(s: &str) -> String {
    let cleaned: String = s
        .chars()
        .map(|c| if c.is_alphanumeric() || c == ' ' { c } else { ' ' })
        .collect();
    let tokens: Vec<&str> = cleaned.split_whitespace().take(8).collect();
    if tokens.is_empty() {
        return String::new();
    }
    tokens
        .iter()
        .map(|t| format!("\"{t}\""))
        .collect::<Vec<_>>()
        .join(" OR ")
}
