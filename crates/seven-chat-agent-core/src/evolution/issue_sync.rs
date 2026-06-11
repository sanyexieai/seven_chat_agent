use chrono::Utc;
use uuid::Uuid;

use super::config::{EvolutionLoopConfig, EvolutionSettings};
use super::github::{
    create_issue, parse_github_repo, resolve_github_token, search_similar_issues, title_similarity,
    trusted_owner, GitHubRepo,
};
use super::optimization::{IssueSyncAction, IssueSyncReport, IssueSyncResult, OptimizationItem};
use super::registry::{EvolutionRegistry, LocalIssueRecord, LocalIssueStatus};
use crate::{Error, Result};

pub async fn sync_issues_for_items(
    settings: &EvolutionSettings,
    registry: &mut EvolutionRegistry,
    items: &[OptimizationItem],
    max_items: u32,
) -> Result<IssueSyncReport> {
    let source = settings
        .source
        .as_ref()
        .ok_or_else(|| Error::bad_request("未配置 source"))?;
    let repo = parse_github_repo(&source.remote_url)
        .ok_or_else(|| Error::bad_request("仅支持 GitHub 远程 URL"))?;
    if !trusted_owner(&settings.evolution, &repo.owner) {
        return Err(Error::bad_request(format!(
            "仓库 owner `{}` 不在 trusted_orgs 白名单",
            repo.owner
        )));
    }
    let token = resolve_github_token(&settings.evolution).ok_or_else(|| {
        Error::bad_request("请配置 GITHUB_TOKEN 环境变量或 evolution.github_token")
    })?;

    let threshold = settings.evolution.issue_similarity_threshold;
    let mut results = Vec::new();
    let mut processed = 0u32;

    for item in items.iter().take(max_items as usize) {
        processed += 1;
        let result = sync_one_item(
            &settings.evolution,
            &repo,
            token.as_str(),
            registry,
            item,
            threshold,
        )
        .await;
        results.push(result);
    }

    Ok(IssueSyncReport {
        items_processed: processed,
        results,
    })
}

async fn sync_one_item(
    evo: &EvolutionLoopConfig,
    repo: &GitHubRepo,
    token: &str,
    registry: &mut EvolutionRegistry,
    item: &OptimizationItem,
    threshold: f32,
) -> IssueSyncResult {
    if let Some(existing) = find_registry_match(registry, item, threshold) {
        boost_relevance(registry, &existing.local_id, &item.related_paths);
        return IssueSyncResult {
            item_id: item.id.clone(),
            item_title: item.title.clone(),
            action: IssueSyncAction::LinkedExisting,
            remote_url: existing.remote_url.clone(),
            local_id: Some(existing.local_id),
            detail: "与本地注册表 issue 相似，已关联".into(),
        };
    }

    let remote_matches = match search_similar_issues(token, repo, &item.title, 5).await {
        Ok(v) => v,
        Err(e) => {
            return IssueSyncResult {
                item_id: item.id.clone(),
                item_title: item.title.clone(),
                action: IssueSyncAction::Skipped,
                remote_url: None,
                local_id: None,
                detail: format!("GitHub 搜索失败: {e}"),
            };
        }
    };

    if let Some(hit) = remote_matches.iter().find(|i| {
        title_similarity(&i.title, &item.title) >= threshold
    }) {
        let local_id = register_linked(registry, item, &hit.html_url, &hit.title);
        return IssueSyncResult {
            item_id: item.id.clone(),
            item_title: item.title.clone(),
            action: IssueSyncAction::LinkedExisting,
            remote_url: Some(hit.html_url.clone()),
            local_id: Some(local_id),
            detail: format!("关联已有远程 issue #{}", hit.number),
        };
    }

    if evo.require_approval_before_create_issue {
        let local_id = register_pending(registry, item);
        return IssueSyncResult {
            item_id: item.id.clone(),
            item_title: item.title.clone(),
            action: IssueSyncAction::PendingApproval,
            remote_url: None,
            local_id: Some(local_id),
            detail: "待审批：可在关闭审批后重试或手动创建".into(),
        };
    }

    let body = format_issue_body(item);
    let labels = evo.default_issue_labels.clone();
    match create_issue(token, repo, &item.title, &body, &labels).await {
        Ok(created) => {
            let local_id = register_linked(registry, item, &created.html_url, &created.title);
            IssueSyncResult {
                item_id: item.id.clone(),
                item_title: item.title.clone(),
                action: IssueSyncAction::CreatedRemote,
                remote_url: Some(created.html_url),
                local_id: Some(local_id),
                detail: format!("已创建远程 issue #{}", created.number),
            }
        }
        Err(e) => IssueSyncResult {
            item_id: item.id.clone(),
            item_title: item.title.clone(),
            action: IssueSyncAction::Skipped,
            remote_url: None,
            local_id: None,
            detail: e.to_string(),
        },
    }
}

fn find_registry_match(
    registry: &EvolutionRegistry,
    item: &OptimizationItem,
    threshold: f32,
) -> Option<LocalIssueRecord> {
    registry
        .issues
        .iter()
        .filter(|i| i.status != LocalIssueStatus::Wontfix)
        .find(|i| {
            title_similarity(&i.relevance_notes, &item.title) >= threshold
                || title_similarity(&item.title, &i.relevance_notes) >= threshold
                || i.related_paths
                    .iter()
                    .any(|p| item.related_paths.iter().any(|rp| rp == p))
        })
        .cloned()
}

fn boost_relevance(registry: &mut EvolutionRegistry, local_id: &str, paths: &[String]) {
    if let Some(i) = registry.issues.iter_mut().find(|x| x.local_id == local_id) {
        i.relevance_boost = (i.relevance_boost + 0.15).min(1.0);
        for p in paths {
            if !i.related_paths.contains(p) {
                i.related_paths.push(p.clone());
            }
        }
    }
}

fn register_linked(
    registry: &mut EvolutionRegistry,
    item: &OptimizationItem,
    remote_url: &str,
    title: &str,
) -> String {
    let local_id = format!("evo-{}", Uuid::new_v4());
    registry.upsert_issue(LocalIssueRecord {
        local_id: local_id.clone(),
        remote_url: Some(remote_url.to_string()),
        first_seen_at: Utc::now(),
        relevance_notes: title.to_string(),
        relevance_boost: 0.2,
        status: LocalIssueStatus::Open,
        related_paths: item.related_paths.clone(),
        claimed_at: None,
    });
    local_id
}

fn register_pending(registry: &mut EvolutionRegistry, item: &OptimizationItem) -> String {
    let local_id = format!("evo-{}", Uuid::new_v4());
    registry.upsert_issue(LocalIssueRecord {
        local_id: local_id.clone(),
        remote_url: None,
        first_seen_at: Utc::now(),
        relevance_notes: item.title.clone(),
        relevance_boost: 0.1,
        status: LocalIssueStatus::Open,
        related_paths: item.related_paths.clone(),
        claimed_at: None,
    });
    local_id
}

fn format_issue_body(item: &OptimizationItem) -> String {
    format!(
        "## 摘要\n{}\n\n## 建议\n{}\n\n## 相关路径\n{}\n\n---\n*由 Seven Chat Agent 进化外环自动提出（source: {}）*",
        item.summary,
        item.suggestion,
        if item.related_paths.is_empty() {
            "（无）".into()
        } else {
            item.related_paths.join("\n")
        },
        item.source
    )
}
