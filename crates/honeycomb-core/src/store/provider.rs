use chrono::Utc;
use uuid::Uuid;

use crate::domain::ProviderKey;
use crate::store::SqliteStore;
use crate::{Error, Result};

#[derive(Debug, sqlx::FromRow)]
struct ProviderKeyRow {
    id: String,
    provider_id: String,
    label: String,
    secret_ref: String,
    rpm_limit: Option<i64>,
    tpm_limit: Option<i64>,
    monthly_budget_usd: Option<f64>,
    current_spent_usd: f64,
    status: String,
}

impl From<ProviderKeyRow> for ProviderKey {
    fn from(r: ProviderKeyRow) -> Self {
        ProviderKey {
            id: r.id,
            provider_id: r.provider_id,
            label: r.label,
            secret_ref: r.secret_ref,
            rpm_limit: r.rpm_limit,
            tpm_limit: r.tpm_limit,
            monthly_budget_usd: r.monthly_budget_usd,
            current_spent_usd: r.current_spent_usd,
            status: r.status,
        }
    }
}

#[derive(Debug, serde::Deserialize)]
pub struct UpsertProviderKey {
    pub id: Option<String>,
    pub provider_id: String,
    pub label: String,
    /// 新建必填；更新时留空或省略表示不修改密钥。
    #[serde(default)]
    pub secret: Option<String>,
    pub rpm_limit: Option<i64>,
    pub tpm_limit: Option<i64>,
    pub monthly_budget_usd: Option<f64>,
}

impl SqliteStore {
    pub async fn list_provider_keys(&self, provider_id: Option<&str>) -> Result<Vec<ProviderKey>> {
        let rows: Vec<ProviderKeyRow> = if let Some(p) = provider_id {
            sqlx::query_as(
                "SELECT id, provider_id, label, secret_ref, rpm_limit, tpm_limit, monthly_budget_usd, current_spent_usd, status FROM provider_keys WHERE provider_id = ? ORDER BY label",
            )
            .bind(p)
            .fetch_all(self.pool())
            .await?
        } else {
            sqlx::query_as(
                "SELECT id, provider_id, label, secret_ref, rpm_limit, tpm_limit, monthly_budget_usd, current_spent_usd, status FROM provider_keys ORDER BY provider_id, label",
            )
            .fetch_all(self.pool())
            .await?
        };
        Ok(rows.into_iter().map(Into::into).collect())
    }

    pub async fn get_provider_key(&self, id: &str) -> Result<Option<ProviderKey>> {
        let row: Option<ProviderKeyRow> = sqlx::query_as(
            "SELECT id, provider_id, label, secret_ref, rpm_limit, tpm_limit, monthly_budget_usd, current_spent_usd, status FROM provider_keys WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(self.pool())
        .await?;
        Ok(row.map(Into::into))
    }

    pub async fn upsert_provider_key(&self, req: UpsertProviderKey) -> Result<ProviderKey> {
        let id = req.id.unwrap_or_else(|| Uuid::new_v4().to_string());
        let now = Utc::now().to_rfc3339();

        let exists: i64 = sqlx::query_scalar("SELECT COUNT(1) FROM provider_keys WHERE id = ?")
            .bind(&id)
            .fetch_one(self.pool())
            .await?;

        let secret_ref = if exists == 0 {
            let secret = req
                .secret
                .as_deref()
                .map(str::trim)
                .filter(|s| !s.is_empty())
                .ok_or_else(|| {
                    crate::Error::bad_request("新建 API Key 时必须填写密钥")
                })?;
            let secret_ref = format!("vault:{}", id);
            self.vault.set(&secret_ref, secret)?;
            secret_ref
        } else {
            let existing = self
                .get_provider_key(&id)
                .await?
                .ok_or_else(|| crate::Error::not_found(format!("provider key {id}")))?;
            if let Some(secret) = req.secret.as_deref().map(str::trim).filter(|s| !s.is_empty()) {
                self.vault.set(&existing.secret_ref, secret)?;
            }
            existing.secret_ref
        };

        if exists == 0 {
            sqlx::query(
                "INSERT INTO provider_keys (id, provider_id, label, secret_ref, rpm_limit, tpm_limit, monthly_budget_usd, current_spent_usd, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'active', ?)",
            )
            .bind(&id)
            .bind(&req.provider_id)
            .bind(&req.label)
            .bind(&secret_ref)
            .bind(req.rpm_limit)
            .bind(req.tpm_limit)
            .bind(req.monthly_budget_usd)
            .bind(&now)
            .execute(self.pool())
            .await?;
        } else {
            sqlx::query(
                "UPDATE provider_keys SET label=?, secret_ref=?, rpm_limit=?, tpm_limit=?, monthly_budget_usd=? WHERE id = ?",
            )
            .bind(&req.label)
            .bind(&secret_ref)
            .bind(req.rpm_limit)
            .bind(req.tpm_limit)
            .bind(req.monthly_budget_usd)
            .bind(&id)
            .execute(self.pool())
            .await?;
        }

        self.get_provider_key(&id)
            .await?
            .ok_or_else(|| Error::not_found("provider key after upsert"))
    }

    pub async fn delete_provider_key(&self, id: &str) -> Result<()> {
        let key = self.get_provider_key(id).await?;
        if let Some(k) = key {
            self.vault.delete(&k.secret_ref).ok();
        }
        sqlx::query("DELETE FROM provider_keys WHERE id = ?")
            .bind(id)
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn record_usage(
        &self,
        key_id: &str,
        input_tokens: i64,
        output_tokens: i64,
        provider_price_input: f64,
        provider_price_output: f64,
    ) -> Result<()> {
        let added =
            (input_tokens as f64 / 1_000_000.0) * provider_price_input
                + (output_tokens as f64 / 1_000_000.0) * provider_price_output;
        sqlx::query(
            "UPDATE provider_keys SET current_spent_usd = current_spent_usd + ?, status = CASE WHEN monthly_budget_usd IS NOT NULL AND current_spent_usd + ? >= monthly_budget_usd THEN 'exhausted' ELSE status END WHERE id = ?",
        )
        .bind(added)
        .bind(added)
        .bind(key_id)
        .execute(self.pool())
        .await?;
        Ok(())
    }
}
