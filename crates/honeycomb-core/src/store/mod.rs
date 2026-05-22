pub mod conversation;
pub mod friend;
pub mod group;
pub mod human;
pub mod memory;
pub mod message;
pub mod provider;
pub mod skill;
pub mod vault;

use std::path::Path;
use std::str::FromStr;

use sqlx::sqlite::{SqliteConnectOptions, SqliteJournalMode, SqlitePoolOptions, SqliteSynchronous};
use sqlx::SqlitePool;

use crate::domain::{BackendKind, Friend, Provider, ProviderCapabilities, ProviderPrice};
use crate::Result;

pub use vault::SecretVault;

#[derive(Clone)]
pub struct SqliteStore {
    pool: SqlitePool,
    pub vault: SecretVault,
}

impl SqliteStore {
    pub async fn connect(database_url: &str) -> Result<Self> {
        let opts = SqliteConnectOptions::from_str(database_url)
            .map_err(|e| crate::Error::Config(e.to_string()))?
            .create_if_missing(true)
            .journal_mode(SqliteJournalMode::Wal)
            .synchronous(SqliteSynchronous::Normal)
            .foreign_keys(true);

        if let Some(parent) = parent_of_db(database_url) {
            if !parent.as_os_str().is_empty() {
                tokio::fs::create_dir_all(&parent).await.ok();
            }
        }

        let pool = SqlitePoolOptions::new()
            .max_connections(8)
            .connect_with(opts)
            .await?;

        let vault = SecretVault::new();

        Ok(Self { pool, vault })
    }

    pub fn pool(&self) -> &SqlitePool {
        &self.pool
    }

    pub async fn migrate(&self) -> Result<()> {
        sqlx::migrate!("../../migrations").run(&self.pool).await?;
        Ok(())
    }

    /// `backend_kind=assistant` 已废弃：统一为 `pty` + `worker-bee-cli` 工蜂实例。
    pub async fn migrate_legacy_assistant_friends(&self) -> Result<()> {
        use crate::domain::AssistantBackendConfig;

        let rows: Vec<(String, String)> = sqlx::query_as(
            "SELECT id, backend_config FROM friends WHERE backend_kind = 'assistant'",
        )
        .fetch_all(&self.pool)
        .await?;

        for (id, cfg_raw) in rows {
            let cfg: AssistantBackendConfig =
                serde_json::from_str(&cfg_raw).unwrap_or_default();
            let skills_dir = if cfg.skills_dir.trim().is_empty() {
                "data/skills".to_string()
            } else {
                cfg.skills_dir
            };
            let pty_cfg = serde_json::json!({
                "preset": "worker-bee-cli",
                "cmd": "worker-bee",
                "args": [],
                "provider_id": cfg.provider_id,
                "model": cfg.model,
                "api_key_id": cfg.api_key_id,
                "skills_dir": skills_dir,
                "memory_top_k": cfg.memory_top_k,
            });
            sqlx::query(
                "UPDATE friends SET backend_kind = 'pty', backend_config = ? WHERE id = ?",
            )
            .bind(pty_cfg.to_string())
            .bind(&id)
            .execute(&self.pool)
            .await?;
            tracing::info!(friend_id = %id, "migrated assistant → pty worker-bee-cli");
        }
        Ok(())
    }

    /// 修复 `preset=null` 的工蜂/内置好友，避免被当成外部 `claude` CLI。
    pub async fn migrate_fixup_pty_worker_bee_configs(&self) -> Result<()> {
        use crate::domain::PtyBackendConfig;
        use crate::friend_cli::{normalize_pty_config, pty_preset_is_worker_bee};

        let rows: Vec<(String, String, i64)> = sqlx::query_as(
            "SELECT id, backend_config, is_builtin FROM friends WHERE backend_kind = 'pty'",
        )
        .fetch_all(&self.pool)
        .await?;

        for (id, cfg_raw, is_builtin) in rows {
            let mut cfg: PtyBackendConfig =
                serde_json::from_str(&cfg_raw).unwrap_or_default();
            normalize_pty_config(&mut cfg, is_builtin != 0);
            if is_builtin == 0 && !pty_preset_is_worker_bee(&cfg) {
                continue;
            }
            let json = serde_json::to_string(&cfg)?;
            if json == cfg_raw {
                continue;
            }
            sqlx::query("UPDATE friends SET backend_config = ? WHERE id = ?")
                .bind(&json)
                .bind(&id)
                .execute(&self.pool)
                .await?;
            tracing::info!(
                friend_id = %id,
                preset = ?cfg.preset,
                "fixed pty backend_config for worker-bee"
            );
        }
        Ok(())
    }

    pub async fn seed_builtins(&self) -> Result<()> {
        // 自愈：历史上判断条件曾经只看 backend_kind='assistant'，
        // 如果用户把内置 Hex 改成了 pty/api 等其它后端，下次启动就会再插一条。
        // 这里先把多余的同名 builtin Hex 降级为普通好友（is_builtin=0），
        // 保留 created_at 最早的那条，不删除任何对话/消息数据。
        sqlx::query(
            r#"UPDATE friends SET is_builtin = 0
               WHERE is_builtin = 1
                 AND name = 'Hex 助理'
                 AND id NOT IN (
                     SELECT id FROM friends
                      WHERE is_builtin = 1 AND name = 'Hex 助理'
                      ORDER BY created_at ASC LIMIT 1
                 )"#,
        )
        .execute(&self.pool)
        .await?;

        // 只要还存在 _任意_ builtin 朋友就不再 seed（原先按 backend_kind 判断会漏）。
        let existing =
            sqlx::query_scalar::<_, i64>("SELECT COUNT(1) FROM friends WHERE is_builtin = 1")
                .fetch_one(&self.pool)
                .await?;
        if existing > 0 {
            return Ok(());
        }

        let id = uuid::Uuid::new_v4().to_string();
        let cfg = serde_json::json!({
            "preset": "worker-bee-cli",
            "cmd": "worker-bee",
            "args": [],
            "provider_id": "",
            "model": "",
            "api_key_id": null,
            "skills_dir": "data/skills",
            "memory_top_k": 5
        });
        let system_prompt = "你是 honeycomb 内置 Agent Hex（工蜂实例）。\n- 你有长期记忆和可进化的技能库；\n- 你乐于协调其他好友、为主人总结、记录约定；\n- 你说话亲切自然，但不啰嗦。".to_string();

        sqlx::query(
            r#"INSERT INTO friends
                (id, name, avatar, system_prompt, personality, focus_tags, backend_kind, backend_config, is_builtin)
                VALUES (?, ?, NULL, ?, ?, ?, 'pty', ?, 1)"#,
        )
        .bind(&id)
        .bind("Hex 助理")
        .bind(&system_prompt)
        .bind("温和、敏锐、爱学习")
        .bind(serde_json::Value::Array(vec![
            serde_json::Value::String("总结".into()),
            serde_json::Value::String("协调".into()),
            serde_json::Value::String("记忆".into()),
        ]).to_string())
        .bind(cfg.to_string())
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn upsert_provider(&self, p: &Provider) -> Result<()> {
        let caps = serde_json::to_string(&p.capabilities)?;
        let price = serde_json::to_string(&p.price)?;
        sqlx::query(
            r#"INSERT INTO providers (id, kind, display_name, base_url, default_model, capabilities, price, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   kind = excluded.kind,
                   display_name = excluded.display_name,
                   base_url = excluded.base_url,
                   default_model = excluded.default_model,
                   capabilities = excluded.capabilities,
                   price = excluded.price,
                   enabled = excluded.enabled"#,
        )
        .bind(&p.id)
        .bind(&p.kind)
        .bind(&p.display_name)
        .bind(&p.base_url)
        .bind(&p.default_model)
        .bind(caps)
        .bind(price)
        .bind(p.enabled)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn list_providers(&self) -> Result<Vec<Provider>> {
        let rows = sqlx::query_as::<_, ProviderRow>(
            "SELECT id, kind, display_name, base_url, default_model, capabilities, price, enabled, created_at FROM providers ORDER BY display_name",
        )
        .fetch_all(&self.pool)
        .await?;
        rows.into_iter().map(|r| r.into_provider()).collect()
    }

    pub async fn delete_provider(&self, id: &str) -> Result<()> {
        // provider_keys 在 init.sql 里是 ON DELETE CASCADE，会自动跟着删
        sqlx::query("DELETE FROM providers WHERE id = ?")
            .bind(id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn get_provider(&self, id: &str) -> Result<Option<Provider>> {
        let row = sqlx::query_as::<_, ProviderRow>(
            "SELECT id, kind, display_name, base_url, default_model, capabilities, price, enabled, created_at FROM providers WHERE id = ?",
        )
        .bind(id)
        .fetch_optional(&self.pool)
        .await?;
        row.map(|r| r.into_provider()).transpose()
    }

    pub fn friend_kind_from_str(s: &str) -> Option<BackendKind> {
        BackendKind::parse(s)
    }

    pub fn friend_from_row(row: friend::FriendRow) -> Result<Friend> {
        row.into_friend()
    }
}

fn parent_of_db(url: &str) -> Option<std::path::PathBuf> {
    let path = url.strip_prefix("sqlite://").unwrap_or(url);
    let path = path.split('?').next().unwrap_or(path);
    if path.is_empty() || path == ":memory:" {
        return None;
    }
    Path::new(path).parent().map(|p| p.to_path_buf())
}

#[derive(Debug, sqlx::FromRow)]
pub(crate) struct ProviderRow {
    pub id: String,
    pub kind: String,
    pub display_name: String,
    pub base_url: String,
    pub default_model: Option<String>,
    pub capabilities: String,
    pub price: String,
    pub enabled: i64,
    pub created_at: String,
}

impl ProviderRow {
    fn into_provider(self) -> Result<Provider> {
        let caps: ProviderCapabilities = serde_json::from_str(&self.capabilities).unwrap_or_default();
        let price: ProviderPrice = serde_json::from_str(&self.price).unwrap_or_default();
        let created_at = parse_dt(&self.created_at);
        Ok(Provider {
            id: self.id,
            kind: self.kind,
            display_name: self.display_name,
            base_url: self.base_url,
            default_model: self.default_model,
            capabilities: caps,
            price,
            enabled: self.enabled != 0,
            created_at,
        })
    }
}

pub(crate) fn parse_dt(s: &str) -> chrono::DateTime<chrono::Utc> {
    chrono::DateTime::parse_from_rfc3339(s)
        .map(|d| d.with_timezone(&chrono::Utc))
        .unwrap_or_else(|_| chrono::Utc::now())
}
