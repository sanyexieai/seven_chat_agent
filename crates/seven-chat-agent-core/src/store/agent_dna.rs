use chrono::Utc;

use crate::agent_dna::{default_dna_principles, AgentDna};
use crate::store::SqliteStore;
use crate::Result;

impl SqliteStore {
    pub async fn ensure_agent_dna(&self) -> Result<()> {
        let tenant_id = self.tenant_id();
        let exists: Option<(i64,)> =
            sqlx::query_as("SELECT 1 FROM agent_dna WHERE tenant_id = ?")
                .bind(tenant_id)
                .fetch_optional(self.pool())
                .await?;
        if exists.is_some() {
            return Ok(());
        }
        let dna = AgentDna::default();
        self.upsert_agent_dna(dna).await?;
        Ok(())
    }

    pub async fn get_agent_dna(&self) -> Result<AgentDna> {
        let row: Option<(String, String)> = sqlx::query_as(
            "SELECT settings, updated_at FROM agent_dna WHERE tenant_id = ?",
        )
        .bind(self.tenant_id())
        .fetch_optional(self.pool())
        .await?;
        let Some((settings, updated_at)) = row else {
            return Ok(AgentDna::default());
        };
        let mut dna: AgentDna = serde_json::from_str(&settings).unwrap_or_default();
        dna.updated_at = Some(crate::store::parse_dt(&updated_at));
        Ok(dna)
    }

    pub async fn upsert_agent_dna(&self, mut dna: AgentDna) -> Result<AgentDna> {
        if dna.principles.is_empty() {
            dna.principles = default_dna_principles();
        }
        dna.updated_at = None;
        let now = Utc::now().to_rfc3339();
        let json = serde_json::to_string(&dna)?;
        sqlx::query(
            r#"INSERT INTO agent_dna (tenant_id, settings, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(tenant_id) DO UPDATE SET
                   settings = excluded.settings,
                   updated_at = excluded.updated_at"#,
        )
        .bind(self.tenant_id())
        .bind(&json)
        .bind(&now)
        .execute(self.pool())
        .await?;
        self.get_agent_dna().await
    }

    pub async fn prepend_tenant_dna(&self, base: &str) -> Result<String> {
        let dna = self.get_agent_dna().await?;
        Ok(crate::agent_dna::prepend_dna(base, &dna))
    }
}
