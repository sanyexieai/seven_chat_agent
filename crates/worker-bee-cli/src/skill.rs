use std::path::{Path, PathBuf};

use anyhow::Result;

#[derive(Debug, Clone)]
pub struct SkillDoc {
    pub name: String,
    pub path: PathBuf,
    pub description: String,
}

/// 扫描目录下的 `SKILL.md`（一级子目录或根目录）。
pub fn scan(skills_dir: &Path) -> Result<Vec<SkillDoc>> {
    let mut out = Vec::new();
    if !skills_dir.is_dir() {
        return Ok(out);
    }
    for entry in std::fs::read_dir(skills_dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_file() && path.file_name().and_then(|n| n.to_str()) == Some("SKILL.md") {
            out.push(read_skill(&path, skills_dir)?);
        } else if path.is_dir() {
            let skill_md = path.join("SKILL.md");
            if skill_md.is_file() {
                out.push(read_skill(&skill_md, &path)?);
            }
        }
    }
    Ok(out)
}

fn read_skill(path: &Path, name_base: &Path) -> Result<SkillDoc> {
    let raw = std::fs::read_to_string(path)?;
    let name = name_base
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("skill")
        .to_string();
    let description = raw
        .lines()
        .find(|l| !l.trim().is_empty() && !l.starts_with('#'))
        .unwrap_or("（无描述）")
        .trim()
        .chars()
        .take(200)
        .collect();
    Ok(SkillDoc {
        name,
        path: path.to_path_buf(),
        description,
    })
}

pub fn format_skills_block(skills: &[SkillDoc]) -> String {
    if skills.is_empty() {
        return String::new();
    }
    let mut s = String::from("\n\n[可用 Skill]\n");
    for sk in skills {
        s.push_str(&format!("- {}: {}\n", sk.name, sk.description));
    }
    s
}
