use std::path::PathBuf;

use anyhow::Result;
use clap::{Parser, Subcommand};

use crate::exec::{run as run_exec, ExecOptions};

#[derive(Parser, Debug)]
#[command(
    name = "worker-bee",
    about = "Worker Bee (工蜂) — honeycomb agent CLI",
    version
)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand, Debug)]
pub enum Commands {
    /// 执行一轮 Agent 任务（兼容 honeycomb codex-exec JSONL）。
    Exec {
        #[arg(value_name = "PROMPT")]
        prompt: Option<String>,

        #[arg(short = 'C', long = "cd")]
        workspace: Option<PathBuf>,

        #[arg(long = "json", default_value_t = false)]
        json: bool,

        #[arg(long = "skip-git-repo-check", default_value_t = false)]
        skip_git_repo_check: bool,

        #[arg(long = "color", default_value = "never")]
        color: String,
    },
}

pub async fn run() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Exec {
            prompt,
            workspace,
            json,
            skip_git_repo_check,
            color,
        } => {
            let workspace = workspace
                .or_else(|| std::env::var("WORKER_BEE_WORKSPACE").ok().map(PathBuf::from))
                .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
            let prompt = match prompt {
                Some(p) if !p.trim().is_empty() => p,
                _ => read_stdin_prompt()?,
            };
            run_exec(ExecOptions {
                workspace,
                prompt,
                json,
                color_never: color == "never",
                skip_git_repo_check,
            })
            .await
        }
    }
}

fn read_stdin_prompt() -> Result<String> {
    use std::io::Read;
    let mut buf = String::new();
    std::io::stdin().read_to_string(&mut buf)?;
    Ok(buf.trim().to_string())
}
