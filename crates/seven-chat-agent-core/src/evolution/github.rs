use serde::{Deserialize, Serialize};

use super::config::EvolutionLoopConfig;
use crate::{Error, Result};

#[derive(Debug, Clone)]
pub struct GitHubRepo {
    pub owner: String,
    pub repo: String,
}

pub fn parse_github_repo(remote_url: &str) -> Option<GitHubRepo> {
    let t = remote_url.trim().trim_end_matches(".git");
    let rest = t.strip_prefix("https://github.com/")?;
    let mut parts = rest.split('/');
    let owner = parts.next()?.to_string();
    let repo = parts.next()?.to_string();
    if owner.is_empty() || repo.is_empty() {
        return None;
    }
    Some(GitHubRepo { owner, repo })
}

pub fn resolve_github_token(cfg: &EvolutionLoopConfig) -> Option<String> {
    if let Some(t) = cfg
        .github_token
        .as_ref()
        .filter(|s| !s.trim().is_empty())
    {
        return Some(t.trim().to_string());
    }
    let env_key = if cfg.github_token_env.trim().is_empty() {
        "GITHUB_TOKEN"
    } else {
        cfg.github_token_env.as_str()
    };
    std::env::var(env_key).ok().filter(|s| !s.trim().is_empty())
}

pub fn trusted_owner(cfg: &EvolutionLoopConfig, owner: &str) -> bool {
    if cfg.trusted_orgs.is_empty() {
        return true;
    }
    cfg.trusted_orgs
        .iter()
        .any(|o| o.eq_ignore_ascii_case(owner))
}

#[derive(Debug, Clone, Deserialize)]
pub struct GitHubIssueSearchItem {
    pub number: u64,
    pub title: String,
    pub html_url: String,
    pub state: String,
}

#[derive(Debug, Deserialize)]
struct SearchResponse {
    items: Vec<GitHubIssueSearchItem>,
}

pub async fn search_similar_issues(
    token: &str,
    repo: &GitHubRepo,
    query_title: &str,
    limit: u32,
) -> Result<Vec<GitHubIssueSearchItem>> {
    let q = format!(
        "repo:{}/{} is:issue is:open {}",
        repo.owner,
        repo.repo,
        escape_query(query_title)
    );
    let url = format!(
        "https://api.github.com/search/issues?q={}&per_page={}",
        urlencoding_encode(&q),
        limit.min(10)
    );
    let client = reqwest::Client::new();
    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {token}"))
        .header("Accept", "application/vnd.github+json")
        .header("User-Agent", "seven-chat-agent-evolution")
        .send()
        .await
        .map_err(|e| Error::Config(format!("github search: {e}")))?;
    if !resp.status().is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err(Error::Config(format!("github search HTTP: {body}")));
    }
    let parsed: SearchResponse = resp
        .json()
        .await
        .map_err(|e| Error::Config(format!("github search parse: {e}")))?;
    Ok(parsed.items)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateIssueResponse {
    pub number: u64,
    pub html_url: String,
    pub title: String,
}

pub async fn create_issue(
    token: &str,
    repo: &GitHubRepo,
    title: &str,
    body: &str,
    labels: &[String],
) -> Result<CreateIssueResponse> {
    let url = format!(
        "https://api.github.com/repos/{}/{}/issues",
        repo.owner, repo.repo
    );
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {token}"))
        .header("Accept", "application/vnd.github+json")
        .header("User-Agent", "seven-chat-agent-evolution")
        .json(&serde_json::json!({
            "title": title,
            "body": body,
            "labels": labels,
        }))
        .send()
        .await
        .map_err(|e| Error::Config(format!("github create: {e}")))?;
    if !resp.status().is_success() {
        let text = resp.text().await.unwrap_or_default();
        return Err(Error::Config(format!("github create HTTP: {text}")));
    }
    let parsed: CreateIssueResponse = resp
        .json()
        .await
        .map_err(|e| Error::Config(format!("github create parse: {e}")))?;
    Ok(parsed)
}

fn escape_query(s: &str) -> String {
    s.split_whitespace()
        .take(6)
        .collect::<Vec<_>>()
        .join(" ")
}

fn urlencoding_encode(s: &str) -> String {
    s.chars()
        .map(|c| match c {
            'a'..='z' | 'A'..='Z' | '0'..='9' | '-' | '_' | '.' | '~' => c.to_string(),
            ' ' => "+".into(),
            _ => format!("%{:02X}", c as u8),
        })
        .collect()
}

pub fn title_similarity(a: &str, b: &str) -> f32 {
    seven_chat_agent_judge::text_similarity(a, b)
}
