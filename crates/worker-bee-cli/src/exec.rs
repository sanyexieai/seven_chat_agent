use std::path::PathBuf;

use anyhow::{bail, Result};

use crate::jsonl::emit_agent_message;
use crate::memory::{format_recall_block, Memory};
use crate::mcp::{format_mcp_block, load_servers};
use crate::skill::{format_skills_block, scan};

#[derive(Debug, Clone)]
pub struct ExecOptions {
    pub workspace: PathBuf,
    pub prompt: String,
    pub json: bool,
    pub color_never: bool,
    pub skip_git_repo_check: bool,
}

pub async fn run(opts: ExecOptions) -> Result<()> {
    let _ = opts.color_never;
    if opts.prompt.trim().is_empty() {
        bail!("exec: prompt is empty");
    }

    let data_dir = resolve_data_dir(&opts.workspace);
    let skills_dir = resolve_skills_dir(&opts.workspace);

    if !opts.skip_git_repo_check {
        let git = opts.workspace.join(".git");
        if !git.exists() {
            eprintln!(
                "worker-bee: workspace is not a git repo ({})",
                opts.workspace.display()
            );
        }
    }

    let mut memory = Memory::open(&data_dir)?;
    let recalled = memory.recall_top(5);
    let skills = scan(&skills_dir)?;
    let mcp_servers = load_servers(&data_dir)?;

    let context = format!(
        "{}{}{}",
        format_recall_block(&recalled),
        format_skills_block(&skills),
        format_mcp_block(&mcp_servers),
    );

    let reply = synthesize_reply(&opts.prompt, &context);
    let summary = truncate(&opts.prompt, 120);
    memory.append(format!("Q: {summary} → A: {}", truncate(&reply, 160)))?;

    if opts.json {
        println!("{}", emit_agent_message(&reply));
    } else {
        println!("{reply}");
    }
    Ok(())
}

fn synthesize_reply(prompt: &str, context: &str) -> String {
    let mut out = format!("【Worker Bee】已收到你的请求。\n\n{prompt}\n");
    if !context.trim().is_empty() {
        out.push_str("\n---\n已加载上下文：");
        out.push_str(context);
        out.push_str(
            "\n---\n提示：配置模型 API 或扩展 worker-bee-cli 推理模块后，此处将输出完整 Agent 回复。",
        );
    } else {
        out.push_str(
            "\n（暂无记忆 / Skill / MCP 配置；可在工作区 `.worker-bee/` 与 `skills/` 下添加。）",
        );
    }
    out
}

fn resolve_data_dir(workspace: &PathBuf) -> PathBuf {
    std::env::var("WORKER_BEE_DATA")
        .map(PathBuf::from)
        .unwrap_or_else(|_| workspace.join(".worker-bee"))
}

fn resolve_skills_dir(workspace: &PathBuf) -> PathBuf {
    std::env::var("WORKER_BEE_SKILLS_DIR")
        .map(PathBuf::from)
        .or_else(|_| std::env::var("SEVEN_CHAT_AGENT_SKILLS_DIR").map(PathBuf::from))
        .unwrap_or_else(|_| {
            let ws = workspace.join("skills");
            if ws.is_dir() {
                ws
            } else {
                PathBuf::from("data/skills")
            }
        })
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        s.chars().take(max).collect::<String>() + "…"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exec_options_build() {
        let opts = ExecOptions {
            workspace: PathBuf::from("/tmp"),
            prompt: "hi".into(),
            json: true,
            color_never: true,
            skip_git_repo_check: true,
        };
        assert_eq!(opts.prompt, "hi");
        assert!(resolve_data_dir(&opts.workspace).ends_with(".worker-bee"));
    }
}
