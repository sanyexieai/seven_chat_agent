use chrono::Utc;
use uuid::Uuid;

use crate::profile::types::ProfileFrameworkCatalog;
use crate::store::SqliteStore;
use crate::{Error, Result};

#[derive(Debug, sqlx::FromRow)]
struct CustomFrameworkRow {
    id: String,
    name: String,
    catalog: String,
    created_at: String,
}

#[derive(Debug, serde::Deserialize)]
pub struct UpsertProfileFramework {
    pub id: Option<String>,
    pub name: String,
    pub catalog: ProfileFrameworkCatalog,
}

impl SqliteStore {
    pub async fn list_custom_profile_frameworks(&self) -> Result<Vec<ProfileFrameworkCatalog>> {
        let rows = sqlx::query_as::<_, CustomFrameworkRow>(
            "SELECT id, name, catalog, created_at FROM profile_frameworks_custom WHERE tenant_id = ? ORDER BY created_at ASC",
        )
        .bind(self.tenant_id())
        .fetch_all(self.pool())
        .await?;
        rows.into_iter()
            .map(|r| {
                let mut c: ProfileFrameworkCatalog =
                    serde_json::from_str(&r.catalog).unwrap_or_else(|_| ProfileFrameworkCatalog {
                        id: r.id.clone(),
                        name: r.name,
                        version: "1".into(),
                        types: vec![],
                        extensions_schema: None,
                    });
                if c.id.is_empty() {
                    c.id = r.id;
                }
                Ok(c)
            })
            .collect()
    }

    pub async fn upsert_custom_profile_framework(
        &self,
        req: UpsertProfileFramework,
    ) -> Result<ProfileFrameworkCatalog> {
        if req.catalog.types.is_empty() {
            return Err(Error::bad_request("framework 至少包含一个 type"));
        }
        crate::profile::validate_framework_extensions_schema(&req.catalog)?;
        let id = req
            .id
            .or_else(|| Some(req.catalog.id.clone()))
            .unwrap_or_else(|| Uuid::new_v4().to_string());
        if id == "mbti_16" || id == "agent_24" {
            return Err(Error::bad_request("不可覆盖内置 framework id"));
        }
        let mut catalog = req.catalog;
        catalog.id = id.clone();
        if catalog.name.is_empty() {
            catalog.name = req.name.clone();
        }
        let catalog_json = serde_json::to_string(&catalog)?;
        let now = Utc::now().to_rfc3339();
        sqlx::query(
            r#"INSERT INTO profile_frameworks_custom (id, tenant_id, name, catalog, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name = excluded.name, catalog = excluded.catalog"#,
        )
        .bind(&id)
        .bind(self.tenant_id())
        .bind(&req.name)
        .bind(&catalog_json)
        .bind(&now)
        .execute(self.pool())
        .await?;
        Ok(catalog)
    }

    pub async fn delete_custom_profile_framework(&self, id: &str) -> Result<()> {
        if id == "mbti_16" || id == "agent_24" {
            return Err(Error::bad_request("不可删除内置 framework"));
        }
        sqlx::query("DELETE FROM profile_frameworks_custom WHERE id = ? AND tenant_id = ?")
            .bind(id)
            .bind(self.tenant_id())
            .execute(self.pool())
            .await?;
        Ok(())
    }

    pub async fn all_profile_frameworks(&self) -> Result<Vec<ProfileFrameworkCatalog>> {
        let mut out: Vec<ProfileFrameworkCatalog> = crate::profile::list_frameworks()
            .iter()
            .cloned()
            .collect();
        out.extend(self.list_custom_profile_frameworks().await?);
        Ok(out)
    }

}
