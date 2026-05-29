use chrono::Utc;
use uuid::Uuid;

use crate::domain::{
    AssistantMode, AssistantPolicyTemplate, AutonomyClassifier, AutonomyLevel,
    GroupAssistantSettings,
};
use crate::store::{parse_dt, SqliteStore};
use crate::{Error, Result};

#[derive(Debug, sqlx::FromRow)]
struct TemplateRow {
    id: String,
    name: String,
    description: Option<String>,
    settings: String,
    created_at: String,
}

impl TemplateRow {
    fn into_template(self) -> Result<AssistantPolicyTemplate> {
        let settings: GroupAssistantSettings =
            serde_json::from_str(&self.settings).unwrap_or_default();
        Ok(AssistantPolicyTemplate {
            id: self.id,
            name: self.name,
            description: self.description,
            settings,
            created_at: parse_dt(&self.created_at),
        })
    }
}

#[derive(Debug, serde::Deserialize)]
pub struct UpsertAssistantPolicyTemplate {
    pub id: Option<String>,
    pub name: String,
    pub description: Option<String>,
    pub settings: GroupAssistantSettings,
}

impl SqliteStore {
    pub async fn list_assistant_policy_templates(&self) -> Result<Vec<AssistantPolicyTemplate>> {
        let rows = sqlx::query_as::<_, TemplateRow>(
            "SELECT id, name, description, settings, created_at FROM assistant_policy_templates ORDER BY created_at ASC",
        )
        .fetch_all(self.pool())
        .await?;
        rows.into_iter().map(|r| r.into_template()).collect()
    }

    pub async fn get_assistant_policy_template(
        &self,
        id: &str,
    ) -> Result<Option<AssistantPolicyTemplate>> {
        let row = sqlx::query_as::<_, TemplateRow>(
            "SELECT id, name, description, settings, created_at FROM assistant_policy_templates WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(self.pool())
        .await?;
        row.map(|r| r.into_template()).transpose()
    }

    pub async fn upsert_assistant_policy_template(
        &self,
        req: UpsertAssistantPolicyTemplate,
    ) -> Result<AssistantPolicyTemplate> {
        let id = req.id.unwrap_or_else(|| Uuid::new_v4().to_string());
        let mut settings = req.settings;
        settings.template_id = None;
        let settings_json = serde_json::to_string(&settings)?;
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            r#"INSERT INTO assistant_policy_templates (id, name, description, settings, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name = excluded.name,
                   description = excluded.description,
                   settings = excluded.settings"#,
        )
        .bind(&id)
        .bind(&req.name)
        .bind(&req.description)
        .bind(&settings_json)
        .bind(&now)
        .execute(self.pool())
        .await?;
        self.get_assistant_policy_template(&id)
            .await?
            .ok_or_else(|| Error::not_found("template after upsert"))
    }

    pub async fn delete_assistant_policy_template(&self, id: &str) -> Result<()> {
        sqlx::query("DELETE FROM assistant_policy_templates WHERE id = ?")
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    /// 解析群内联 + 可选模板的有效助理策略。
    pub async fn resolve_group_assistant_settings(
        &self,
        inline: &GroupAssistantSettings,
    ) -> Result<GroupAssistantSettings> {
        let Some(tid) = inline.template_id.as_deref() else {
            return Ok(inline.clone());
        };
        let Some(tpl) = self.get_assistant_policy_template(tid).await? else {
            tracing::warn!(template_id = %tid, "assistant policy template missing");
            return Ok(inline.clone());
        };
        Ok(inline.merge_with_template(&tpl.settings))
    }

    pub async fn seed_assistant_policy_templates(&self) -> Result<()> {
        let count: i64 =
            sqlx::query_scalar("SELECT COUNT(1) FROM assistant_policy_templates")
                .fetch_one(self.pool())
                .await?;
        if count > 0 {
            return Ok(());
        }

        let presets: &[(&str, &str, Option<&str>, GroupAssistantSettings)] = &[
            (
                "preset-delegate",
                "默认代你",
                Some("小事代发，L2 内自动代答，以上待确认"),
                GroupAssistantSettings {
                    enabled: true,
                    mode: AssistantMode::Delegate,
                    max_autonomy: AutonomyLevel::L2,
                    reply_after_experts: true,
                    template_id: None,
                    autonomy_classifier: AutonomyClassifier::Auto,
                    classifier_provider_id: None,
                    classifier_model: None,
                    ..GroupAssistantSettings::default()
                },
            ),
            (
                "preset-strict",
                "严格确认",
                Some("仅 L1 可代发，其余须确认；LLM 分类优先"),
                GroupAssistantSettings {
                    enabled: true,
                    mode: AssistantMode::Delegate,
                    max_autonomy: AutonomyLevel::L1,
                    reply_after_experts: true,
                    template_id: None,
                    autonomy_classifier: AutonomyClassifier::Auto,
                    classifier_provider_id: None,
                    classifier_model: None,
                    ..GroupAssistantSettings::default()
                },
            ),
            (
                "preset-observe",
                "仅观察",
                Some("助理不代发，仅记录"),
                GroupAssistantSettings {
                    enabled: true,
                    mode: AssistantMode::Observe,
                    max_autonomy: AutonomyLevel::L0,
                    reply_after_experts: false,
                    template_id: None,
                    autonomy_classifier: AutonomyClassifier::Heuristic,
                    classifier_provider_id: None,
                    classifier_model: None,
                    ..GroupAssistantSettings::default()
                },
            ),
            (
                "preset-moderate",
                "主持调解",
                Some("仅 @助理 时介入，Auto 分类"),
                GroupAssistantSettings {
                    enabled: true,
                    mode: AssistantMode::Moderate,
                    max_autonomy: AutonomyLevel::L2,
                    reply_after_experts: true,
                    template_id: None,
                    autonomy_classifier: AutonomyClassifier::Auto,
                    classifier_provider_id: None,
                    classifier_model: None,
                    ..GroupAssistantSettings::default()
                },
            ),
        ];

        for (id, name, desc, settings) in presets {
            let _ = self
                .upsert_assistant_policy_template(UpsertAssistantPolicyTemplate {
                    id: Some((*id).to_string()),
                    name: (*name).to_string(),
                    description: desc.map(str::to_string),
                    settings: settings.clone(),
                })
                .await?;
        }
        Ok(())
    }
}
