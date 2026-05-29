use chrono::Utc;

use crate::domain::AssistantGlobalSettings;
use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

const GLOBAL_ROW_ID: &str = "global";

impl SqliteStore {
    pub async fn ensure_assistant_global_settings(&self) -> Result<()> {
        let _ = self.get_assistant_global_settings().await?;
        Ok(())
    }
}

#[derive(Debug, sqlx::FromRow)]
struct GlobalRow {
    settings: String,
    updated_at: String,
}

impl SqliteStore {
    pub async fn get_assistant_global_settings(&self) -> Result<AssistantGlobalSettings> {
        let row: Option<GlobalRow> = sqlx::query_as(
            "SELECT settings, updated_at FROM assistant_global_settings WHERE id = ?",
        )
        .bind(GLOBAL_ROW_ID)
        .fetch_optional(self.pool())
        .await?;

        let Some(row) = row else {
            return Ok(AssistantGlobalSettings::default());
        };
        let mut settings: AssistantGlobalSettings =
            serde_json::from_str(&row.settings).unwrap_or_default();
        settings.updated_at = Some(parse_dt(&row.updated_at));
        Ok(settings)
    }

    pub async fn upsert_assistant_global_settings(
        &self,
        mut settings: AssistantGlobalSettings,
    ) -> Result<AssistantGlobalSettings> {
        let current = self.get_assistant_global_settings().await?;
        settings.observe_streak = current.observe_streak;
        settings.monthly_tokens_used = current.monthly_tokens_used;
        settings.budget_period_ym = current.budget_period_ym;
        settings.updated_at = None;

        let now = Utc::now().to_rfc3339();
        let json = serde_json::to_string(&settings)?;
        sqlx::query(
            r#"INSERT INTO assistant_global_settings (id, settings, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   settings = excluded.settings,
                   updated_at = excluded.updated_at"#,
        )
        .bind(GLOBAL_ROW_ID)
        .bind(&json)
        .bind(&now)
        .execute(self.pool())
        .await?;

        self.get_assistant_global_settings().await
    }

    /// 观察写入后递增计数，达到阈值时整理记忆并归零计数。
    pub async fn touch_observe_consolidate(
        &self,
        assistant_id: &str,
        settings: &AssistantGlobalSettings,
    ) -> Result<()> {
        if !settings.auto_consolidate {
            return Ok(());
        }
        let every = settings.consolidate_every_n.max(1);
        let mut current = self.get_assistant_global_settings().await?;
        current.observe_streak = current.observe_streak.saturating_add(1);
        if current.observe_streak >= every {
            self.consolidate_memories(assistant_id).await?;
            current.observe_streak = 0;
        }
        current.updated_at = None;
        let now = Utc::now().to_rfc3339();
        let json = serde_json::to_string(&current)?;
        sqlx::query(
            "UPDATE assistant_global_settings SET settings = ?, updated_at = ? WHERE id = ?",
        )
        .bind(&json)
        .bind(&now)
        .bind(GLOBAL_ROW_ID)
        .execute(self.pool())
        .await?;
        Ok(())
    }

    pub async fn consolidate_assistant_memories(&self) -> Result<()> {
        let assistant_id = self
            .builtin_assistant_id()
            .await?
            .ok_or_else(|| Error::not_found("builtin assistant"))?;
        self.consolidate_memories(&assistant_id).await?;
        let mut settings = self.get_assistant_global_settings().await?;
        settings.observe_streak = 0;
        settings.updated_at = None;
        let now = Utc::now().to_rfc3339();
        let json = serde_json::to_string(&settings)?;
        sqlx::query(
            "UPDATE assistant_global_settings SET settings = ?, updated_at = ? WHERE id = ?",
        )
        .bind(&json)
        .bind(&now)
        .bind(GLOBAL_ROW_ID)
        .execute(self.pool())
        .await?;
        Ok(())
    }

    pub async fn consume_assistant_tokens(&self, used_tokens: u64) -> Result<AssistantGlobalSettings> {
        let mut settings = self.get_assistant_global_settings().await?;
        let ym = Utc::now().format("%Y-%m").to_string();
        if settings.budget_period_ym.as_deref() != Some(ym.as_str()) {
            settings.budget_period_ym = Some(ym);
            settings.monthly_tokens_used = 0;
        }
        settings.monthly_tokens_used = settings.monthly_tokens_used.saturating_add(used_tokens);
        settings.updated_at = None;
        let now = Utc::now().to_rfc3339();
        let json = serde_json::to_string(&settings)?;
        sqlx::query(
            "UPDATE assistant_global_settings SET settings = ?, updated_at = ? WHERE id = ?",
        )
        .bind(&json)
        .bind(&now)
        .bind(GLOBAL_ROW_ID)
        .execute(self.pool())
        .await?;
        self.get_assistant_global_settings().await
    }

    pub fn assistant_budget_available(&self, settings: &AssistantGlobalSettings) -> bool {
        settings.monthly_token_budget == 0
            || settings.monthly_tokens_used < settings.monthly_token_budget
    }
}
