use std::fs;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use serde::{Deserialize, Serialize};

use crate::agent::assistant::guard::{scan, GuardReport};
use crate::Result;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillFrontmatter {
    pub name: String,
    #[serde(default = "default_version")]
    pub version: u32,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub triggers: Vec<String>,
    #[serde(default)]
    pub requires_toolsets: Vec<String>,
    #[serde(default)]
    pub platforms: Vec<String>,
    #[serde(default = "default_trust")]
    pub trust_level: String,
}

fn default_version() -> u32 {
    1
}
fn default_trust() -> String {
    "agent_created".to_string()
}

#[derive(Debug, Clone)]
pub struct LoadedSkill {
    pub name: String,
    pub path: PathBuf,
    pub summary: String,
    pub frontmatter: SkillFrontmatter,
    pub body: String,
    pub guard: GuardReport,
    pub mtime: SystemTime,
}

#[derive(Debug)]
pub struct SkillLibrary {
    root: PathBuf,
    owner_friend_id: String,
    skills: Vec<LoadedSkill>,
}

impl SkillLibrary {
    pub fn new(root: impl Into<PathBuf>, owner_friend_id: String) -> Self {
        let mut s = Self {
            root: root.into(),
            owner_friend_id,
            skills: vec![],
        };
        s.reload();
        s
    }

    pub fn reload(&mut self) {
        self.skills.clear();
        let dir = self.root.join(&self.owner_friend_id);
        let _ = fs::create_dir_all(&dir);
        let entries = match fs::read_dir(&dir) {
            Ok(e) => e,
            Err(_) => return,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("md") {
                continue;
            }
            if let Some(sk) = load_skill_file(&path) {
                self.skills.push(sk);
            }
        }
    }

    pub fn tier1_index(&self, lowered_prompt: &str) -> Vec<LoadedSkillSummary> {
        let mut out = Vec::new();
        for sk in &self.skills {
            if matches_triggers(&sk.frontmatter.triggers, lowered_prompt) {
                out.push(LoadedSkillSummary {
                    name: sk.name.clone(),
                    summary: sk.summary.clone(),
                });
            }
        }
        out
    }

    pub fn get_by_name(&self, name: &str) -> Option<&LoadedSkill> {
        self.skills.iter().find(|s| s.name == name)
    }

    pub fn create_or_update(
        &mut self,
        frontmatter: SkillFrontmatter,
        body: &str,
    ) -> Result<LoadedSkill> {
        let dir = self.root.join(&self.owner_friend_id);
        fs::create_dir_all(&dir)?;
        let safe_name = sanitize_name(&frontmatter.name);
        let path = dir.join(format!("{safe_name}.md"));
        let tmp = dir.join(format!(".{safe_name}.md.tmp"));
        let yaml = serde_yaml_pretty(&frontmatter);
        let document = format!("---\n{yaml}---\n\n{}\n", body.trim());
        fs::write(&tmp, document.as_bytes())?;
        fs::rename(&tmp, &path)?;
        if let Some(sk) = load_skill_file(&path) {
            self.skills.retain(|s| s.name != sk.name);
            self.skills.push(sk.clone());
            return Ok(sk);
        }
        Err(crate::Error::Other(anyhow::anyhow!(
            "failed to load skill after write"
        )))
    }
}

#[derive(Debug, Clone)]
pub struct LoadedSkillSummary {
    pub name: String,
    pub summary: String,
}

fn matches_triggers(triggers: &[String], prompt_lower: &str) -> bool {
    if triggers.is_empty() {
        return false;
    }
    triggers.iter().any(|t| {
        let needle = t.to_lowercase();
        !needle.is_empty() && prompt_lower.contains(&needle)
    })
}

fn sanitize_name(s: &str) -> String {
    s.chars()
        .map(|c| {
            if c.is_alphanumeric() || c == '_' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

fn load_skill_file(path: &Path) -> Option<LoadedSkill> {
    let raw = fs::read_to_string(path).ok()?;
    let (frontmatter, body) = split_frontmatter(&raw)?;
    let fm: SkillFrontmatter = serde_yaml_parse(&frontmatter)?;
    let guard = scan(&raw);
    let summary = body
        .lines()
        .filter(|l| !l.trim().is_empty())
        .skip_while(|l| l.starts_with('#'))
        .next()
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|| fm.description.clone());
    Some(LoadedSkill {
        name: fm.name.clone(),
        path: path.to_path_buf(),
        summary,
        frontmatter: fm,
        body: body.to_string(),
        guard,
        mtime: fs::metadata(path)
            .and_then(|m| m.modified())
            .unwrap_or_else(|_| SystemTime::now()),
    })
}

fn split_frontmatter(raw: &str) -> Option<(String, String)> {
    let raw = raw.trim_start();
    let rest = raw.strip_prefix("---")?;
    let end = rest.find("\n---")?;
    let frontmatter = rest[..end].trim_start_matches('\n');
    let body = &rest[end + 4..];
    let body = body.strip_prefix('\n').unwrap_or(body);
    Some((frontmatter.to_string(), body.to_string()))
}

fn serde_yaml_pretty(fm: &SkillFrontmatter) -> String {
    let mut out = String::new();
    out.push_str(&format!("name: {}\n", fm.name));
    out.push_str(&format!("version: {}\n", fm.version));
    if !fm.description.is_empty() {
        out.push_str(&format!("description: {}\n", escape_yaml(&fm.description)));
    }
    out.push_str(&format!("trust_level: {}\n", fm.trust_level));
    if !fm.triggers.is_empty() {
        out.push_str("triggers:\n");
        for t in &fm.triggers {
            out.push_str(&format!("  - {}\n", escape_yaml(t)));
        }
    }
    if !fm.requires_toolsets.is_empty() {
        out.push_str("requires_toolsets:\n");
        for t in &fm.requires_toolsets {
            out.push_str(&format!("  - {}\n", escape_yaml(t)));
        }
    }
    if !fm.platforms.is_empty() {
        out.push_str("platforms:\n");
        for t in &fm.platforms {
            out.push_str(&format!("  - {}\n", t));
        }
    }
    out
}

fn escape_yaml(s: &str) -> String {
    if s.contains(':') || s.contains('#') || s.contains('\n') || s.starts_with('-') {
        format!("\"{}\"", s.replace('"', "\\\""))
    } else {
        s.to_string()
    }
}

fn serde_yaml_parse(yaml: &str) -> Option<SkillFrontmatter> {
    let mut name = String::new();
    let mut version: u32 = 1;
    let mut description = String::new();
    let mut triggers = Vec::new();
    let mut requires_toolsets = Vec::new();
    let mut platforms = Vec::new();
    let mut trust = "agent_created".to_string();

    enum Block {
        None,
        Triggers,
        Toolsets,
        Platforms,
    }
    let mut block = Block::None;
    for raw_line in yaml.lines() {
        let line = raw_line.trim_end();
        if line.is_empty() {
            block = Block::None;
            continue;
        }
        if let Some(rest) = line.strip_prefix("  - ") {
            let value = unquote(rest.trim()).to_string();
            match block {
                Block::Triggers => triggers.push(value),
                Block::Toolsets => requires_toolsets.push(value),
                Block::Platforms => platforms.push(value),
                Block::None => {}
            }
            continue;
        }
        block = Block::None;
        if let Some((k, v)) = line.split_once(':') {
            let value = v.trim();
            match k.trim() {
                "name" => name = unquote(value).to_string(),
                "version" => version = value.parse().unwrap_or(1),
                "description" => description = unquote(value).to_string(),
                "trust_level" => trust = unquote(value).to_string(),
                "triggers" if value.is_empty() => block = Block::Triggers,
                "requires_toolsets" if value.is_empty() => block = Block::Toolsets,
                "platforms" if value.is_empty() => block = Block::Platforms,
                _ => {}
            }
        }
    }
    if name.is_empty() {
        return None;
    }
    Some(SkillFrontmatter {
        name,
        version,
        description,
        triggers,
        requires_toolsets,
        platforms,
        trust_level: trust,
    })
}

fn unquote(s: &str) -> &str {
    if s.starts_with('"') && s.ends_with('"') && s.len() >= 2 {
        &s[1..s.len() - 1]
    } else {
        s
    }
}
