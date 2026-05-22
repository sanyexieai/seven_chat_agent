use chrono::Utc;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Skill {
    pub id: String,
    pub owner_friend_id: String,
    pub name: String,
    pub version: i64,
    pub path: String,
    pub description: String,
    pub triggers: Vec<String>,
    pub requires_toolsets: Vec<String>,
    pub platforms: Vec<String>,
    pub trust_level: String,
    pub guard_report: serde_json::Value,
    pub enabled: bool,
    pub created_at: chrono::DateTime<chrono::Utc>,
    pub updated_at: chrono::DateTime<chrono::Utc>,
}

#[derive(Debug, sqlx::FromRow)]
struct SkillRow {
    id: String,
    owner_friend_id: String,
    name: String,
    version: i64,
    path: String,
    description: String,
    triggers: String,
    requires_toolsets: String,
    platforms: String,
    trust_level: String,
    guard_report: String,
    enabled: i64,
    created_at: String,
    updated_at: String,
}

impl From<SkillRow> for Skill {
    fn from(r: SkillRow) -> Self {
        Skill {
            id: r.id,
            owner_friend_id: r.owner_friend_id,
            name: r.name,
            version: r.version,
            path: r.path,
            description: r.description,
            triggers: serde_json::from_str(&r.triggers).unwrap_or_default(),
            requires_toolsets: serde_json::from_str(&r.requires_toolsets).unwrap_or_default(),
            platforms: serde_json::from_str(&r.platforms).unwrap_or_default(),
            trust_level: r.trust_level,
            guard_report: serde_json::from_str(&r.guard_report)
                .unwrap_or(serde_json::Value::Object(Default::default())),
            enabled: r.enabled != 0,
            created_at: parse_dt(&r.created_at),
            updated_at: parse_dt(&r.updated_at),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpsertSkill {
    pub owner_friend_id: String,
    pub name: String,
    pub path: String,
    pub description: String,
    #[serde(default)]
    pub triggers: Vec<String>,
    #[serde(default)]
    pub requires_toolsets: Vec<String>,
    #[serde(default)]
    pub platforms: Vec<String>,
    pub trust_level: String,
    #[serde(default)]
    pub guard_report: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NewSkillRun {
    pub owner_friend_id: String,
    pub skill_id: Option<String>,
    pub candidate_name: Option<String>,
    pub message_id: Option<String>,
    pub succeeded: bool,
    pub duration_ms: i64,
    pub patch_applied: bool,
    pub notes: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Reflection {
    pub id: String,
    pub owner_friend_id: String,
    pub turn_id: String,
    pub score: f64,
    pub summary: String,
    pub lessons: Vec<String>,
    pub created_at: chrono::DateTime<chrono::Utc>,
}

#[derive(Debug, sqlx::FromRow)]
struct ReflectionRow {
    id: String,
    owner_friend_id: String,
    turn_id: String,
    score: f64,
    summary: String,
    lessons: String,
    created_at: String,
}

impl From<ReflectionRow> for Reflection {
    fn from(r: ReflectionRow) -> Self {
        Reflection {
            id: r.id,
            owner_friend_id: r.owner_friend_id,
            turn_id: r.turn_id,
            score: r.score,
            summary: r.summary,
            lessons: serde_json::from_str(&r.lessons).unwrap_or_default(),
            created_at: parse_dt(&r.created_at),
        }
    }
}

impl SqliteStore {
    pub async fn list_skills(&self, owner: &str) -> Result<Vec<Skill>> {
        let rows: Vec<SkillRow> = sqlx::query_as(
            "SELECT id, owner_friend_id, name, version, path, description, triggers, requires_toolsets, platforms, trust_level, guard_report, enabled, created_at, updated_at FROM skills WHERE owner_friend_id = ? ORDER BY updated_at DESC",
        )
        .bind(owner)
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(Skill::from).collect())
    }

    pub async fn upsert_skill(&self, req: UpsertSkill) -> Result<Skill> {
        let triggers = serde_json::to_string(&req.triggers)?;
        let toolsets = serde_json::to_string(&req.requires_toolsets)?;
        let platforms = serde_json::to_string(&req.platforms)?;
        let guard = serde_json::to_string(&req.guard_report)?;
        let now = Utc::now().to_rfc3339();
        let existing: Option<SkillRow> = sqlx::query_as(
            "SELECT id, owner_friend_id, name, version, path, description, triggers, requires_toolsets, platforms, trust_level, guard_report, enabled, created_at, updated_at FROM skills WHERE owner_friend_id = ? AND name = ?",
        )
        .bind(&req.owner_friend_id)
        .bind(&req.name)
        .fetch_optional(self.pool())
        .await?;
        if let Some(r) = existing {
            sqlx::query(
                "UPDATE skills SET version = version + 1, path = ?, description = ?, triggers = ?, requires_toolsets = ?, platforms = ?, trust_level = ?, guard_report = ?, updated_at = ? WHERE id = ?",
            )
            .bind(&req.path)
            .bind(&req.description)
            .bind(&triggers)
            .bind(&toolsets)
            .bind(&platforms)
            .bind(&req.trust_level)
            .bind(&guard)
            .bind(&now)
            .bind(&r.id)
            .execute(self.pool())
            .await?;
            return self.get_skill(&r.id).await?.ok_or_else(|| Error::not_found("skill after update"));
        }
        let id = Uuid::new_v4().to_string();
        sqlx::query(
            "INSERT INTO skills (id, owner_friend_id, name, version, path, description, triggers, requires_toolsets, platforms, trust_level, guard_report, enabled, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
        )
        .bind(&id)
        .bind(&req.owner_friend_id)
        .bind(&req.name)
        .bind(&req.path)
        .bind(&req.description)
        .bind(&triggers)
        .bind(&toolsets)
        .bind(&platforms)
        .bind(&req.trust_level)
        .bind(&guard)
        .bind(&now)
        .bind(&now)
        .execute(self.pool())
        .await?;
        self.get_skill(&id)
            .await?
            .ok_or_else(|| Error::not_found("skill after insert"))
    }

    pub async fn get_skill(&self, id: &str) -> Result<Option<Skill>> {
        let row: Option<SkillRow> = sqlx::query_as(
            "SELECT id, owner_friend_id, name, version, path, description, triggers, requires_toolsets, platforms, trust_level, guard_report, enabled, created_at, updated_at FROM skills WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(Skill::from))
    }

    pub async fn delete_skill(&self, id: &str) -> Result<()> {
        sqlx::query("DELETE FROM skills WHERE id = ?")
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn record_skill_run(&self, req: NewSkillRun) -> Result<()> {
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "INSERT INTO skill_runs (id, skill_id, candidate_name, owner_friend_id, message_id, succeeded, duration_ms, patch_applied, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(&id)
        .bind(&req.skill_id)
        .bind(&req.candidate_name)
        .bind(&req.owner_friend_id)
        .bind(&req.message_id)
        .bind(req.succeeded)
        .bind(req.duration_ms)
        .bind(if req.patch_applied { 1 } else { 0 })
        .bind(&req.notes)
        .bind(&now)
        .execute(self.pool())
        .await?;
        Ok(())
    }

    pub async fn count_skill_runs(&self, owner: &str, candidate_name: &str) -> Result<i64> {
        let n: i64 = sqlx::query_scalar(
            "SELECT COUNT(1) FROM skill_runs WHERE owner_friend_id = ? AND candidate_name = ?",
        )
        .bind(owner)
        .bind(candidate_name)
        .fetch_one(self.pool())
        .await?;
        Ok(n)
    }

    pub async fn insert_reflection(
        &self,
        owner: &str,
        turn_id: &str,
        score: f64,
        summary: &str,
        lessons: &[String],
    ) -> Result<()> {
        let id = Uuid::new_v4().to_string();
        let lessons_json = serde_json::to_string(lessons)?;
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            "INSERT INTO reflections (id, owner_friend_id, turn_id, score, summary, lessons, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(&id)
        .bind(owner)
        .bind(turn_id)
        .bind(score)
        .bind(summary)
        .bind(&lessons_json)
        .bind(&now)
        .execute(self.pool())
        .await?;
        Ok(())
    }

    pub async fn list_reflections(&self, owner: &str, limit: i64) -> Result<Vec<Reflection>> {
        let rows: Vec<ReflectionRow> = sqlx::query_as(
            "SELECT id, owner_friend_id, turn_id, score, summary, lessons, created_at FROM reflections WHERE owner_friend_id = ? ORDER BY created_at DESC LIMIT ?",
        )
        .bind(owner)
        .bind(limit)
        .fetch_all(self.pool())
        .await?;
        Ok(rows.into_iter().map(Reflection::from).collect())
    }
}
