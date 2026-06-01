//! 从本机 Codex / Claude / Cursor 目录发现可导入的 CLI 会话。

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};

use chrono::{DateTime, Utc};
use serde_json::Value;

use crate::cli_tool::{TOOL_CLAUDE, TOOL_CODEX, TOOL_CURSOR};
use crate::Result;

/// 统一的外部会话元数据（导入 cli_sessions 用）。
#[derive(Debug, Clone)]
pub struct ExternalCliSessionMeta {
    pub tool: &'static str,
    pub native_session_id: String,
    pub cwd: Option<String>,
    pub first_ask: Option<String>,
    pub source_path: PathBuf,
    pub modified_at: DateTime<Utc>,
    /// Cursor：`~/.cursor/projects/<slug>/` 目录名，用于 cwd 缺失时匹配工作区。
    pub cursor_project_slug: Option<String>,
}

#[derive(Debug, Clone)]
pub struct CodexRolloutMeta {
    pub thread_id: String,
    pub cwd: Option<String>,
    pub first_ask: Option<String>,
    pub source_path: PathBuf,
    pub modified_at: DateTime<Utc>,
}

impl CodexRolloutMeta {
    fn into_external(self) -> ExternalCliSessionMeta {
        ExternalCliSessionMeta {
            tool: TOOL_CODEX,
            native_session_id: self.thread_id,
            cwd: self.cwd,
            first_ask: self.first_ask,
            source_path: self.source_path,
            modified_at: self.modified_at,
            cursor_project_slug: None,
        }
    }
}

pub fn codex_home() -> PathBuf {
    if let Ok(h) = std::env::var("CODEX_HOME") {
        let t = h.trim();
        if !t.is_empty() {
            return PathBuf::from(t);
        }
    }
    std::env::var("HOME")
        .ok()
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".codex")
}

/// 递归扫描 `sessions` 下的 `rollout-*.jsonl`。
pub fn scan_codex_rollouts(codex_home: &Path) -> Vec<CodexRolloutMeta> {
    let sessions = codex_home.join("sessions");
    if !sessions.is_dir() {
        return Vec::new();
    }
    let mut out = Vec::new();
    walk_rollouts(&sessions, &mut out);
    out.sort_by(|a, b| b.modified_at.cmp(&a.modified_at));
    out
}

fn walk_rollouts(dir: &Path, out: &mut Vec<CodexRolloutMeta>) {
    let Ok(read) = std::fs::read_dir(dir) else {
        return;
    };
    for ent in read.flatten() {
        let path = ent.path();
        if path.is_dir() {
            walk_rollouts(&path, out);
            continue;
        }
        if path.extension().and_then(|s| s.to_str()) != Some("jsonl") {
            continue;
        }
        let name = path.file_name().and_then(|s| s.to_str()).unwrap_or("");
        if !name.contains("rollout") {
            continue;
        }
        if let Some(meta) = parse_codex_rollout_file(&path) {
            out.push(meta);
        }
    }
}

fn parse_codex_rollout_file(path: &Path) -> Option<CodexRolloutMeta> {
    let thread_id = extract_rollout_thread_id(path)?;
    let modified_at = std::fs::metadata(path)
        .ok()
        .and_then(|m| m.modified().ok())
        .map(|t| DateTime::<Utc>::from(t))
        .unwrap_or_else(Utc::now);
    let (cwd, first_ask) = read_rollout_preview(path).ok()?;
    Some(CodexRolloutMeta {
        thread_id,
        cwd,
        first_ask,
        source_path: path.to_path_buf(),
        modified_at,
    })
}

/// 文件名 `rollout-...-<uuid>.jsonl` 或 JSONL 内 `thread_id`。
fn extract_rollout_thread_id(path: &Path) -> Option<String> {
    let name = path.file_stem()?.to_str()?;
    if let Some(uuid) = name.rsplit('-').next() {
        if uuid.len() >= 32 && uuid.chars().all(|c| c.is_ascii_hexdigit() || c == '-') {
            return Some(uuid.to_string());
        }
    }
    let file = std::fs::File::open(path).ok()?;
    for line in BufReader::new(file).lines().take(30) {
        let line = line.ok()?;
        let v: Value = serde_json::from_str(&line).ok()?;
        if let Some(id) = v.get("thread_id").and_then(|t| t.as_str()) {
            if !id.is_empty() {
                return Some(id.to_string());
            }
        }
        if let Some(id) = v
            .pointer("/payload/thread_id")
            .and_then(|t| t.as_str())
        {
            if !id.is_empty() {
                return Some(id.to_string());
            }
        }
    }
    None
}

fn read_rollout_preview(path: &Path) -> Result<(Option<String>, Option<String>)> {
    let file = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(_) => return Ok((None, None)),
    };
    let mut cwd = None;
    let mut first_ask = None;
    for line in BufReader::new(file).lines().take(120) {
        let line = line.map_err(crate::Error::Io)?;
        let t = line.trim();
        if t.is_empty() {
            continue;
        }
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue;
        };
        if v.get("record_type").and_then(|r| r.as_str()) == Some("state") {
            continue;
        }
        let role = v
            .get("role")
            .or_else(|| v.pointer("/message/role"))
            .and_then(|r| r.as_str());
        if role != Some("user") {
            continue;
        }
        let text = extract_message_text(&v);
        if text.is_empty() {
            continue;
        }
        if let Some(c) = parse_cwd_from_user_text(&text) {
            cwd.get_or_insert(c);
            continue;
        }
        if is_meta_user_text(&text) {
            continue;
        }
        if first_ask.is_none() {
            first_ask = Some(crate::assistant_accumulation::truncate_chars(&text, 240));
        }
        if cwd.is_some() && first_ask.is_some() {
            break;
        }
    }
    Ok((cwd, first_ask))
}

fn extract_message_text(v: &Value) -> String {
    if let Some(s) = v.get("content").and_then(|c| c.as_str()) {
        return s.to_string();
    }
    if let Some(s) = v.pointer("/message/content").and_then(|c| c.as_str()) {
        return s.to_string();
    }
    if let Some(arr) = v.get("content").and_then(|c| c.as_array()) {
        let mut parts = Vec::new();
        for item in arr {
            if let Some(t) = item.get("text").and_then(|x| x.as_str()) {
                parts.push(t);
            }
        }
        return parts.join("\n");
    }
    if let Some(arr) = v.pointer("/message/content").and_then(|c| c.as_array()) {
        let mut parts = Vec::new();
        for item in arr {
            if let Some(t) = item.get("text").and_then(|x| x.as_str()) {
                parts.push(t);
            }
        }
        return parts.join("\n");
    }
    String::new()
}

fn parse_cwd_from_user_text(text: &str) -> Option<String> {
    for tag in ["<cwd>", "<working_directory>"] {
        if let Some(start) = text.find(tag) {
            let rest = &text[start + tag.len()..];
            if let Some(end) = rest.find('<') {
                let p = rest[..end].trim();
                if !p.is_empty() {
                    return Some(p.to_string());
                }
            }
        }
    }
    None
}

fn is_meta_user_text(text: &str) -> bool {
    let t = text.trim_start();
    t.starts_with("<environment_context>")
        || t.starts_with("<instructions>")
        || t.starts_with("<system_reminder>")
        || t.starts_with("# AGENTS.md")
}

pub fn claude_config_dir() -> PathBuf {
    if let Ok(d) = std::env::var("CLAUDE_CONFIG_DIR") {
        let t = d.trim();
        if !t.is_empty() {
            return PathBuf::from(t);
        }
    }
    std::env::var("HOME")
        .ok()
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".claude")
}

/// 扫描 `~/.claude/projects/<项目编码>/*.jsonl`（不含 subagents 子目录内文件）。
pub fn scan_claude_sessions(claude_dir: &Path) -> Vec<ExternalCliSessionMeta> {
    let projects = claude_dir.join("projects");
    if !projects.is_dir() {
        return Vec::new();
    }
    let mut out = Vec::new();
    let Ok(read) = std::fs::read_dir(&projects) else {
        return out;
    };
    for ent in read.flatten() {
        let project_dir = ent.path();
        if !project_dir.is_dir() {
            continue;
        }
        let Ok(files) = std::fs::read_dir(&project_dir) else {
            continue;
        };
        for f in files.flatten() {
            let path = f.path();
            if !path.is_file() {
                continue;
            }
            if path.extension().and_then(|s| s.to_str()) != Some("jsonl") {
                continue;
            }
            if let Some(meta) = parse_claude_session_file(&path) {
                out.push(meta);
            }
        }
    }
    out.sort_by(|a, b| b.modified_at.cmp(&a.modified_at));
    out
}

fn parse_claude_session_file(path: &Path) -> Option<ExternalCliSessionMeta> {
    let native_session_id = path
        .file_stem()?
        .to_str()?
        .trim()
        .to_string();
    if native_session_id.is_empty() {
        return None;
    }
    let modified_at = file_modified_at(path);
    let (cwd, first_ask, session_from_line) = read_claude_preview(path).ok()?;
    let native_session_id = session_from_line.unwrap_or(native_session_id);
    Some(ExternalCliSessionMeta {
        tool: TOOL_CLAUDE,
        native_session_id,
        cwd,
        first_ask,
        source_path: path.to_path_buf(),
        modified_at,
        cursor_project_slug: None,
    })
}

fn read_claude_preview(path: &Path) -> Result<(Option<String>, Option<String>, Option<String>)> {
    let file = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(_) => return Ok((None, None, None)),
    };
    let mut cwd = None;
    let mut first_ask = None;
    let mut session_id = None;
    for line in BufReader::new(file).lines().take(150) {
        let line = line.map_err(crate::Error::Io)?;
        let t = line.trim();
        if t.is_empty() {
            continue;
        }
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue;
        };
        if cwd.is_none() {
            if let Some(c) = v.get("cwd").and_then(|c| c.as_str()) {
                if !c.trim().is_empty() {
                    cwd = Some(c.trim().to_string());
                }
            }
        }
        if session_id.is_none() {
            if let Some(s) = v.get("sessionId").and_then(|c| c.as_str()) {
                if !s.trim().is_empty() {
                    session_id = Some(s.trim().to_string());
                }
            }
        }
        let msg_type = v.get("type").and_then(|t| t.as_str());
        if msg_type == Some("user") {
            let text = extract_claude_user_text(&v);
            if !text.is_empty() && first_ask.is_none() {
                first_ask = Some(crate::assistant_accumulation::truncate_chars(&text, 240));
            }
        }
        if cwd.is_some() && first_ask.is_some() && session_id.is_some() {
            break;
        }
    }
    Ok((cwd, first_ask, session_id))
}

fn extract_claude_user_text(v: &Value) -> String {
    if let Some(msg) = v.get("message") {
        return extract_message_text(msg);
    }
    extract_message_text(v)
}

pub fn cursor_home() -> PathBuf {
    if let Ok(h) = std::env::var("CURSOR_HOME") {
        let t = h.trim();
        if !t.is_empty() {
            return PathBuf::from(t);
        }
    }
    std::env::var("HOME")
        .ok()
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".cursor")
}

/// 扫描 `~/.cursor/projects/*/agent-transcripts/**/*.jsonl`。
pub fn scan_cursor_agent_transcripts(cursor_home: &Path) -> Vec<ExternalCliSessionMeta> {
    let projects = cursor_home.join("projects");
    if !projects.is_dir() {
        return Vec::new();
    }
    let mut out = Vec::new();
    let Ok(read) = std::fs::read_dir(&projects) else {
        return out;
    };
    for ent in read.flatten() {
        let project_dir = ent.path();
        if !project_dir.is_dir() {
            continue;
        }
        let slug = project_dir
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_string();
        let transcripts = project_dir.join("agent-transcripts");
        if transcripts.is_dir() {
            walk_cursor_transcripts(&transcripts, &slug, &mut out);
        }
    }
    out.sort_by(|a, b| b.modified_at.cmp(&a.modified_at));
    out
}

fn walk_cursor_transcripts(dir: &Path, project_slug: &str, out: &mut Vec<ExternalCliSessionMeta>) {
    let Ok(read) = std::fs::read_dir(dir) else {
        return;
    };
    for ent in read.flatten() {
        let path = ent.path();
        if path.is_dir() {
            walk_cursor_transcripts(&path, project_slug, out);
            continue;
        }
        if path.extension().and_then(|s| s.to_str()) != Some("jsonl") {
            continue;
        }
        if let Some(mut meta) = parse_cursor_transcript_file(&path) {
            meta.cursor_project_slug = Some(project_slug.to_string());
            if meta.cwd.is_none() {
                meta.cwd = decode_cursor_project_slug(project_slug);
            }
            out.push(meta);
        }
    }
}

fn parse_cursor_transcript_file(path: &Path) -> Option<ExternalCliSessionMeta> {
    let native_session_id = path
        .file_stem()?
        .to_str()?
        .trim()
        .to_string();
    if native_session_id.is_empty() {
        return None;
    }
    let modified_at = file_modified_at(path);
    let (cwd, first_ask, id_line) = read_cursor_transcript_preview(path).ok()?;
    Some(ExternalCliSessionMeta {
        tool: TOOL_CURSOR,
        native_session_id: id_line.unwrap_or(native_session_id),
        cwd,
        first_ask,
        source_path: path.to_path_buf(),
        modified_at,
        cursor_project_slug: None,
    })
}

fn read_cursor_transcript_preview(
    path: &Path,
) -> Result<(Option<String>, Option<String>, Option<String>)> {
    let file = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(_) => return Ok((None, None, None)),
    };
    let mut cwd = None;
    let mut first_ask = None;
    let mut chat_id = None;
    for line in BufReader::new(file).lines().take(120) {
        let line = line.map_err(crate::Error::Io)?;
        let t = line.trim();
        if t.is_empty() {
            continue;
        }
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue;
        };
        for key in ["cwd", "workspacePath", "workspace_path"] {
            if cwd.is_none() {
                if let Some(c) = v.get(key).and_then(|c| c.as_str()) {
                    if !c.trim().is_empty() {
                        cwd = Some(c.trim().to_string());
                    }
                }
            }
        }
        for key in ["chatId", "chat_id", "sessionId", "session_id", "conversationId"] {
            if chat_id.is_none() {
                if let Some(c) = v.get(key).and_then(|c| c.as_str()) {
                    if !c.trim().is_empty() {
                        chat_id = Some(c.trim().to_string());
                    }
                }
            }
        }
        let is_user = v.get("role").and_then(|r| r.as_str()) == Some("user")
            || v.get("type").and_then(|t| t.as_str()) == Some("user")
            || v.pointer("/message/role").and_then(|r| r.as_str()) == Some("user");
        if is_user {
            let text = extract_message_text(&v);
            if !text.is_empty() && !is_meta_user_text(&text) && first_ask.is_none() {
                first_ask = Some(crate::assistant_accumulation::truncate_chars(&text, 240));
            }
        }
    }
    Ok((cwd, first_ask, chat_id))
}

/// Cursor 项目目录名（路径中 `/` → `-`）与 workspace 路径模糊匹配。
pub fn cursor_project_slug_matches(workspace_path: &Path, project_slug: &str) -> bool {
    let norm = workspace_path_slugs(workspace_path);
    let proj_lower = project_slug.to_lowercase();
    norm.iter().any(|slug| {
        let slug_lower = slug.to_lowercase();
        proj_lower.contains(&slug_lower)
            || slug_lower.contains(&proj_lower)
            || proj_lower.ends_with(&slug_lower)
            || slug_lower.ends_with(&proj_lower)
    })
}

fn workspace_path_slugs(workspace_path: &Path) -> Vec<String> {
    let mut slugs = Vec::new();
    let raw = workspace_path
        .to_string_lossy()
        .trim_start_matches('/')
        .replace('\\', "/");
    if !raw.is_empty() {
        slugs.push(normalize_path_slug(&raw));
    }
    if let Ok(ws) = crate::cli_workspace::absolutize_path(workspace_path) {
        let c = ws.to_string_lossy().trim_start_matches('/').replace('\\', "/");
        let s = normalize_path_slug(&c);
        if !slugs.contains(&s) {
            slugs.push(s);
        }
    }
    slugs
}

fn normalize_path_slug(path: &str) -> String {
    path.replace('/', "-").replace('_', "-")
}

fn decode_cursor_project_slug(slug: &str) -> Option<String> {
    if slug.is_empty() {
        return None;
    }
    if slug.contains('/') || slug.contains('\\') {
        return Some(slug.to_string());
    }
    if slug.starts_with("mnt-") || slug.contains('-') {
        let pathish = format!("/{}", slug.replace('-', "/"));
        return Some(pathish);
    }
    None
}

fn file_modified_at(path: &Path) -> DateTime<Utc> {
    std::fs::metadata(path)
        .ok()
        .and_then(|m| m.modified().ok())
        .map(|t| DateTime::<Utc>::from(t))
        .unwrap_or_else(Utc::now)
}

/// 判断外部会话 cwd（或 Cursor 项目 slug）是否属于工作区。
pub fn session_matches_workspace(meta: &ExternalCliSessionMeta, workspace_path: &Path) -> bool {
    if path_matches_workspace(meta.cwd.as_deref(), workspace_path) {
        return true;
    }
    if meta.tool == TOOL_CURSOR {
        if let Some(slug) = meta.cursor_project_slug.as_deref() {
            if cursor_project_slug_matches(workspace_path, slug) {
                return true;
            }
        }
    }
    false
}

pub fn scan_codex_as_external(codex_home: &Path) -> Vec<ExternalCliSessionMeta> {
    scan_codex_rollouts(codex_home)
        .into_iter()
        .map(|r| r.into_external())
        .collect()
}

/// 判断 rollout 的 cwd 是否属于该工作区目录。
pub fn path_matches_workspace(rollout_cwd: Option<&str>, workspace_path: &Path) -> bool {
    let Some(cwd) = rollout_cwd.map(str::trim).filter(|s| !s.is_empty()) else {
        return false;
    };
    let Ok(ws) = crate::cli_workspace::absolutize_path(workspace_path) else {
        return false;
    };
    let Ok(rc) = crate::cli_workspace::absolutize_path(Path::new(cwd)) else {
        return false;
    };
    rc == ws || rc.starts_with(ws.as_path())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn meta_user_text_skipped() {
        assert!(is_meta_user_text("<environment_context>foo"));
        assert!(!is_meta_user_text("fix the login bug"));
    }

    #[test]
    fn cursor_slug_matches_workspace_path() {
        let ws = Path::new("/mnt/code_disk/code/ai/seven_chat_agent");
        assert!(cursor_project_slug_matches(
            ws,
            "mnt-code-disk-code-ai-seven-chat-agent"
        ));
    }
}
