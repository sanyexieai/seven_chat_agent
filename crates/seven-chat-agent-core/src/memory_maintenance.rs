//! 记忆维护流水线：过期清理 → 衰减归档 → LLM ingest → 向量回填。

use crate::domain::AssistantGlobalSettings;
use crate::memory_ingest::{
    embed_memory_if_configured, ingest_raw_memories, organize_curated_memories,
    resolve_assistant_inference,
};
use crate::provider::ProviderRegistry;
use crate::store::SqliteStore;
use crate::Result;
use serde::Serialize;

#[derive(Debug, Clone, Default, Serialize)]
pub struct MemoryMaintenanceReport {
    pub expired_deleted: u64,
    pub ingest: crate::memory_ingest::IngestReport,
    pub curated_organize: crate::memory_ingest::CuratedOrganizeReport,
    pub embeddings_updated: u32,
}

pub async fn run_memory_maintenance(
    store: &SqliteStore,
    providers: &ProviderRegistry,
) -> Result<MemoryMaintenanceReport> {
    let settings = store.get_assistant_global_settings().await?;
    let Some(assistant_id) = store.builtin_assistant_id().await? else {
        return Ok(MemoryMaintenanceReport::default());
    };

    let _ = store.archive_expired_memories(&assistant_id).await?;
    let expired_deleted = store.purge_expired_memories(&assistant_id).await?;

    let ingest = if settings.auto_ingest_raw {
        ingest_raw_memories(store, providers, &assistant_id, &settings).await?
    } else {
        Default::default()
    };

    let curated_organize = if settings.auto_ingest_raw {
        organize_curated_memories(store, providers, &assistant_id, &settings).await?
    } else {
        Default::default()
    };

    store.consolidate_memories(&assistant_id).await?;

    let embeddings_updated = if settings.embedding_enabled {
        backfill_embeddings(store, providers, &assistant_id, &settings, 12).await?
    } else {
        0
    };

    Ok(MemoryMaintenanceReport {
        expired_deleted,
        ingest,
        curated_organize,
        embeddings_updated,
    })
}

async fn backfill_embeddings(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    assistant_id: &str,
    settings: &AssistantGlobalSettings,
    limit: i64,
) -> Result<u32> {
    let rows = store
        .list_curated_missing_embedding(assistant_id, limit)
        .await?;
    let (_, _, api_key_id) = resolve_assistant_inference(store, assistant_id).await?;
    let mut updated = 0u32;
    for (id, content) in rows {
        if embed_memory_if_configured(
            store,
            providers,
            settings,
            assistant_id,
            &id,
            &content,
            api_key_id.as_deref(),
        )
        .await
        .is_ok()
        {
            updated += 1;
        }
    }
    Ok(updated)
}
