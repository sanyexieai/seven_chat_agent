//! 用 LLM 将多条 raw 记忆合并为少量 curated（OpenViking 风格 ingest）。

use crate::domain::{AssistantGlobalSettings, PtyBackendConfig};
use crate::llm_json::extract_json_array;
use crate::memory_tier::{self, TIER_CURATED};
use crate::provider::types::{ChatMessage, ProviderEvent};
use crate::provider::ProviderRegistry;
use crate::store::memory::{Memory, NewMemory};
use crate::store::SqliteStore;
use crate::{Error, Result};
use futures::StreamExt;

#[derive(Debug, Clone, Default, serde::Serialize)]
pub struct IngestReport {
    pub raw_considered: usize,
    pub raw_skipped_noise: usize,
    pub curated_created: usize,
    pub raw_archived: usize,
    pub llm_parse_failed: bool,
}

#[derive(Debug, Clone, Default, serde::Serialize)]
pub struct CuratedOrganizeReport {
    pub curated_considered: usize,
    pub updated: usize,
    pub deleted: usize,
}

pub async fn ingest_raw_memories(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    assistant_id: &str,
    settings: &AssistantGlobalSettings,
) -> Result<IngestReport> {
    let mut report = IngestReport::default();
    if !settings.auto_ingest_raw {
        return Ok(report);
    }

    let batch = settings.ingest_raw_batch_size.max(5).min(60) as i64;
    let fetched = store.list_raw_for_ingest(assistant_id, batch).await?;
    report.raw_considered = fetched.len();
    let mut noise_ids = Vec::new();
    let raws: Vec<Memory> = fetched
        .into_iter()
        .filter(|m| {
            if is_ingest_noise_raw(&m.content) {
                noise_ids.push(m.id.clone());
                false
            } else {
                true
            }
        })
        .collect();
    report.raw_skipped_noise = noise_ids.len();
    if !noise_ids.is_empty() {
        report.raw_archived += store.archive_memories_by_ids(&noise_ids).await?;
    }
    if raws.is_empty() {
        return Ok(report);
    }

    let (provider_id, model, api_key_id) = resolve_assistant_inference(store, assistant_id).await?;
    let provider = providers
        .get(&provider_id)
        .ok_or_else(|| Error::provider(format!("provider missing: {provider_id}")))?;

    let tenant = store.tenant_id();
    let raw_block = format_raw_batch(&raws);
    let mut req = crate::provider::types::ChatRequest::new(
        &model,
        vec![
            ChatMessage::system(ingest_system_prompt(tenant)),
            ChatMessage::user(format!(
                "以下 {n} 条原始观察/备忘，请合并为 0~8 条整理记忆。若无稳定可复用事实输出 []。\n\n{raw_block}",
                n = raws.len(),
                raw_block = raw_block,
            )),
        ],
    );
    req.api_key_id = api_key_id.clone();
    req.stream = false;
    req.response_format_json = true;

    let mut stream = provider.chat(req).await?;
    let mut raw_resp = String::new();
    while let Some(item) = stream.next().await {
        if let Ok(ProviderEvent::Token(t)) = item {
            raw_resp.push_str(&t);
        }
    }

    let json = extract_json_array(&raw_resp).unwrap_or_else(|| raw_resp.clone());
    let parsed: serde_json::Value = match serde_json::from_str(&json) {
        Ok(v) => v,
        Err(e) => {
            report.llm_parse_failed = true;
            tracing::warn!(
                err = %e,
                raw_len = raws.len(),
                resp_preview = %raw_resp.chars().take(240).collect::<String>(),
                "memory ingest: LLM JSON parse failed"
            );
            return Ok(report);
        }
    };
    let Some(arr) = parsed.as_array() else {
        tracing::warn!(
            raw_len = raws.len(),
            "memory ingest: LLM returned non-array"
        );
        return Ok(report);
    };
    if arr.is_empty() {
        tracing::info!(
            raw_len = raws.len(),
            "memory ingest: LLM returned empty array (no new curated)"
        );
    }

    let valid_raw_ids: std::collections::HashSet<String> =
        raws.iter().map(|m| m.id.clone()).collect();

    for item in arr {
        let content = item
            .get("content")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string();
        if content.len() < 8 {
            continue;
        }
        let scope = item
            .get("scope")
            .and_then(|v| v.as_str())
            .unwrap_or(memory_tier::SCOPE_GLOBAL);
        let scope_ref = item
            .get("scope_ref")
            .and_then(|v| v.as_str())
            .map(String::from)
            .or_else(|| {
                if scope == memory_tier::SCOPE_USER {
                    Some(tenant.to_string())
                } else {
                    None
                }
            });
        let importance = item
            .get("importance")
            .and_then(|v| v.as_i64())
            .unwrap_or(1) as i32;
        let weight = item
            .get("weight")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.55)
            .clamp(0.0, 1.0);
        let title = item
            .get("title")
            .and_then(|v| v.as_str())
            .map(String::from);
        let summary = item
            .get("summary")
            .and_then(|v| v.as_str())
            .map(String::from)
            .or_else(|| Some(memory_tier::make_summary(&content, 240)));
        let kind = item
            .get("kind")
            .and_then(|v| v.as_str())
            .unwrap_or(crate::assistant_accumulation::MEMORY_KIND_KNOWLEDGE);

        let mut source_ids: Vec<String> = item
            .get("source_raw_ids")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|x| x.as_str().map(String::from))
                    .filter(|id| valid_raw_ids.contains(id))
                    .collect()
            })
            .unwrap_or_default();
        if source_ids.is_empty() {
            source_ids = raws.iter().map(|m| m.id.clone()).take(3).collect();
        }

        let note = if source_ids.is_empty() {
            String::new()
        } else {
            format!("\n[整理自 raw: {}]", source_ids.join(", "))
        };
        let content = format!("{content}{note}");

        let expires_at = if scope == memory_tier::SCOPE_EPHEMERAL {
            Some(store.ephemeral_expires_at(settings))
        } else {
            None
        };

        let inserted = store
            .insert_memory(NewMemory {
                owner_friend_id: assistant_id.to_string(),
                kind: kind.to_string(),
                content,
                source_message_id: None,
                weight,
                pinned: false,
                tier: TIER_CURATED.to_string(),
                scope: scope.to_string(),
                scope_ref,
                importance,
                status: memory_tier::STATUS_ACTIVE.to_string(),
                title,
                summary,
                expires_at,
            })
            .await?;
        report.curated_created += 1;

        if settings.embedding_enabled {
            if let Err(e) = embed_memory_if_configured(
                store,
                providers,
                settings,
                assistant_id,
                &inserted.id,
                &inserted.content,
                api_key_id.as_deref(),
            )
            .await
            {
                tracing::debug!(err = %e, memory_id = %inserted.id, "ingest embed failed");
            }
        }

        let archived = store.archive_memories_by_ids(&source_ids).await?;
        report.raw_archived += archived;
    }

    Ok(report)
}

fn is_ingest_noise_raw(content: &str) -> bool {
    let c = content.trim();
    c.starts_with("[待办执行]")
        || c.starts_with("[待办失败]")
        || c.starts_with("[协助记录]")
}

pub async fn organize_curated_memories(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    assistant_id: &str,
    settings: &AssistantGlobalSettings,
) -> Result<CuratedOrganizeReport> {
    let mut report = CuratedOrganizeReport::default();
    if !settings.auto_ingest_raw {
        return Ok(report);
    }

    let curated = store.list_curated_for_organize(assistant_id, 48).await?;
    report.curated_considered = curated.len();
    if curated.len() < 2 {
        return Ok(report);
    }

    let (provider_id, model, api_key_id) = resolve_assistant_inference(store, assistant_id).await?;
    let provider = providers
        .get(&provider_id)
        .ok_or_else(|| Error::provider(format!("provider missing: {provider_id}")))?;

    let block = curated
        .iter()
        .map(|m| {
            format!(
                "--- id={} kind={} scope={} imp={} ---\n{}\n",
                m.id,
                m.kind,
                m.scope,
                m.importance,
                m.summary.as_deref().unwrap_or(&m.content)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");

    let mut req = crate::provider::types::ChatRequest::new(
        &model,
        vec![
            ChatMessage::system(
                r#"你是记忆库整理器。根据已有 curated 记忆，去重合并并删除噪声。
只输出 JSON 对象（不要 markdown）：
{
  "delete_ids": ["要删除的重复/无价值记忆 id"],
  "updates": [{"id":"...", "content":"...", "title":"...", "summary":"...", "importance":2}]
}
delete_ids 与 updates 可为空数组；不要编造 id。"#,
            ),
            ChatMessage::user(format!(
                "共 {} 条 curated，请整理：\n\n{block}",
                curated.len(),
            )),
        ],
    );
    req.api_key_id = api_key_id.clone();
    req.stream = false;
    req.response_format_json = true;

    let mut stream = provider.chat(req).await?;
    let mut raw_resp = String::new();
    while let Some(item) = stream.next().await {
        if let Ok(ProviderEvent::Token(t)) = item {
            raw_resp.push_str(&t);
        }
    }

    let json = crate::llm_json::extract_json_object(&raw_resp).unwrap_or(raw_resp);
    let v: serde_json::Value = match serde_json::from_str(&json) {
        Ok(v) => v,
        Err(e) => {
            tracing::warn!(
                err = %e,
                curated = curated.len(),
                "curated organize: JSON parse failed"
            );
            return Ok(report);
        }
    };

    let valid_ids: std::collections::HashSet<String> =
        curated.iter().map(|m| m.id.clone()).collect();

    if let Some(del) = v.get("delete_ids").and_then(|a| a.as_array()) {
        for id in del.iter().filter_map(|x| x.as_str()) {
            if !valid_ids.contains(id) {
                continue;
            }
            if store.delete_memory(id).await.is_ok() {
                report.deleted += 1;
            }
        }
    }

    if let Some(updates) = v.get("updates").and_then(|a| a.as_array()) {
        for item in updates {
            let id = match item.get("id").and_then(|x| x.as_str()) {
                Some(s) if valid_ids.contains(s) => s,
                _ => continue,
            };
            let content = item.get("content").and_then(|x| x.as_str());
            let title = match item.get("title") {
                Some(v) => Some(v.as_str()),
                None => None,
            };
            let summary = match item.get("summary") {
                Some(v) => Some(v.as_str()),
                None => None,
            };
            let importance = item
                .get("importance")
                .and_then(|x| x.as_i64())
                .map(|i| i as i32);
            let _ = store
                .update_memory(
                    id,
                    None,
                    content,
                    None,
                    None,
                    None,
                    None,
                    None,
                    importance,
                    None,
                    title,
                    summary,
                    false,
                )
                .await;
            report.updated += 1;
        }
    }

    tracing::info!(
        considered = report.curated_considered,
        updated = report.updated,
        deleted = report.deleted,
        "curated organize done"
    );
    Ok(report)
}

fn ingest_system_prompt(tenant_id: &str) -> String {
    format!(
        r#"你是记忆整理器。把多条原始观察合并为少量可复用 curated 记忆。
只输出 JSON 数组，每项字段：
- kind: knowledge|preference|fact|project|relation|lesson
- content: 简体中文，一条一个核心事实
- scope: global|user|friend|conversation|ephemeral
- scope_ref: 可选 id；user 作用域请用 "{tenant_id}" 表示当前租户用户偏好
- importance: 0-3
- weight: 0~1
- title, summary: 可选短标题与摘要
- source_raw_ids: 引用的原始记忆 id 数组
合并重复、去掉寒暄与流水账；短期排期用 ephemeral。"#,
        tenant_id = tenant_id
    )
}

fn format_raw_batch(raws: &[Memory]) -> String {
    raws.iter()
        .map(|m| {
            format!(
                "--- id={} scope={} created={} ---\n{}",
                m.id,
                m.scope,
                m.created_at.to_rfc3339(),
                m.content
            )
        })
        .collect::<Vec<_>>()
        .join("\n\n")
}

pub async fn resolve_assistant_inference(
    store: &SqliteStore,
    assistant_id: &str,
) -> Result<(String, String, Option<String>)> {
    let friend = store
        .get_friend(assistant_id)
        .await?
        .ok_or_else(|| Error::not_found("assistant friend"))?;
    let cfg: PtyBackendConfig =
        serde_json::from_value(friend.backend_config).unwrap_or_default();
    let resolved = crate::runtime::resolve_worker_bee_provider(
        &cfg.provider_id,
        &cfg.model,
        cfg.api_key_id,
    );
    Ok((
        resolved.provider_id,
        resolved.model,
        resolved.api_key_id,
    ))
}

pub async fn embed_memory_if_configured(
    store: &SqliteStore,
    providers: &ProviderRegistry,
    settings: &AssistantGlobalSettings,
    assistant_id: &str,
    memory_id: &str,
    content: &str,
    api_key_id: Option<&str>,
) -> Result<()> {
    if !settings.embedding_enabled {
        return Ok(());
    }
    let provider_id = if let Some(p) = settings
        .embedding_provider_id
        .as_deref()
        .filter(|s| !s.is_empty())
    {
        p.to_string()
    } else if let Ok((p, _, _)) = resolve_assistant_inference(store, assistant_id).await {
        p
    } else {
        "openai".to_string()
    };
    let model = settings
        .embedding_model
        .as_deref()
        .filter(|s| !s.is_empty())
        .unwrap_or("text-embedding-3-small")
        .to_string();
    let text = memory_tier::make_summary(content, 2000);
    let vec = providers
        .embed_text(&provider_id, &model, &text, api_key_id)
        .await?;
    store.set_memory_embedding(memory_id, &vec).await
}
