use std::path::{Path, PathBuf};
use std::process::Stdio;

use chrono::Utc;
use tokio::process::Command;

use super::config::{EvolutionCliConfig, SourceCenterConfig};
use super::layout::EvolutionLayout;
use super::run_log::EvolutionStepLog;
use crate::{Error, Result};

pub struct BuildCliResult {
    pub steps: Vec<EvolutionStepLog>,
    pub backup_dir: Option<PathBuf>,
    pub built_binary: Option<PathBuf>,
    pub health_ok: bool,
}

pub async fn build_cli(
    layout: &EvolutionLayout,
    cli: &EvolutionCliConfig,
    source: &SourceCenterConfig,
    workspace_dir: &str,
) -> Result<BuildCliResult> {
    let ws_path = layout.workspace_path(workspace_dir);
    if !ws_path.join(".git").exists() && !ws_path.exists() {
        return Err(Error::bad_request("请先执行 sync-source"));
    }

    let mut steps = Vec::new();
    let backup_dir = backup_cli(layout, cli).await?;
    if let Some(ref dir) = backup_dir {
        steps.push(EvolutionStepLog {
            name: "cli_backup".into(),
            ok: true,
            detail: format!("已备份到 {}", dir.display()),
            stdout: String::new(),
            stderr: String::new(),
        });
    } else {
        steps.push(EvolutionStepLog {
            name: "cli_backup".into(),
            ok: true,
            detail: "未配置 cli.binary_path，跳过备份".into(),
            stdout: String::new(),
            stderr: String::new(),
        });
    }

    if source.build_command.trim().is_empty() {
        return Err(Error::bad_request("source.build_command 未配置"));
    }
    let build_step = run_shell_in_workspace(&ws_path, &source.build_command, "source_build").await?;
    let build_ok = build_step.ok;
    steps.push(build_step);
    if !build_ok {
        return Ok(BuildCliResult {
            steps,
            backup_dir,
            built_binary: None,
            health_ok: false,
        });
    }

    let built = ws_path.join(&source.built_binary_path);
    if !built.exists() {
        steps.push(EvolutionStepLog {
            name: "locate_binary".into(),
            ok: false,
            detail: format!("产物不存在: {}", built.display()),
            stdout: String::new(),
            stderr: String::new(),
        });
        return Ok(BuildCliResult {
            steps,
            backup_dir,
            built_binary: None,
            health_ok: false,
        });
    }

    let health = health_check_binary(&built).await?;
    let health_ok = health.ok;
    steps.push(health);
    Ok(BuildCliResult {
        steps,
        backup_dir,
        built_binary: if health_ok { Some(built) } else { None },
        health_ok,
    })
}

async fn backup_cli(layout: &EvolutionLayout, cli: &EvolutionCliConfig) -> Result<Option<PathBuf>> {
    let src = cli.binary_path.trim();
    if src.is_empty() {
        return Ok(None);
    }
    let src_path = Path::new(src);
    if !src_path.exists() {
        return Ok(None);
    }
    let stamp = Utc::now().format("%Y%m%d-%H%M%S").to_string();
    let dest_dir = layout.cli_backup_dir().join(&stamp);
    tokio::fs::create_dir_all(&dest_dir)
        .await
        .map_err(|e| Error::Config(e.to_string()))?;
    let file_name = src_path
        .file_name()
        .map(|s| s.to_os_string())
        .unwrap_or_else(|| "cli".into());
    let dest = dest_dir.join(file_name);
    tokio::fs::copy(src_path, &dest)
        .await
        .map_err(|e| Error::Config(format!("backup copy: {e}")))?;
    let meta_path = dest_dir.join("backup-meta.json");
    let meta = serde_json::json!({
        "source": src,
        "backed_up_at": Utc::now().to_rfc3339(),
    });
    tokio::fs::write(&meta_path, serde_json::to_string_pretty(&meta)?)
        .await
        .map_err(|e| Error::Config(e.to_string()))?;
    Ok(Some(dest_dir))
}

async fn run_shell_in_workspace(
    ws_path: &Path,
    command: &str,
    step_name: &str,
) -> Result<EvolutionStepLog> {
    let out = if cfg!(windows) {
        Command::new("cmd")
            .current_dir(ws_path)
            .args(["/C", command])
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output()
            .await
    } else {
        Command::new("sh")
            .current_dir(ws_path)
            .arg("-c")
            .arg(command)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output()
            .await
    }
    .map_err(|e| Error::Config(format!("{step_name}: {e}")))?;
    Ok(EvolutionStepLog {
        name: step_name.into(),
        ok: out.status.success(),
        detail: if out.status.success() {
            format!("在 {} 执行完成", ws_path.display())
        } else {
            format!("退出码 {:?}", out.status.code())
        },
        stdout: truncate_log(&String::from_utf8_lossy(&out.stdout), 8000),
        stderr: truncate_log(&String::from_utf8_lossy(&out.stderr), 8000),
    })
}

async fn health_check_binary(binary: &Path) -> Result<EvolutionStepLog> {
    let out = Command::new(binary)
        .arg("--help")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await
        .map_err(|e| Error::Config(format!("health check spawn: {e}")))?;
    Ok(EvolutionStepLog {
        name: "cli_health".into(),
        ok: out.status.success(),
        detail: if out.status.success() {
            format!("{} --help 通过", binary.display())
        } else {
            format!("{} --help 失败", binary.display())
        },
        stdout: truncate_log(&String::from_utf8_lossy(&out.stdout), 2000),
        stderr: truncate_log(&String::from_utf8_lossy(&out.stderr), 2000),
    })
}

fn truncate_log(s: &str, max: usize) -> String {
    if s.len() <= max {
        return s.to_string();
    }
    format!("{}…", &s[..max])
}
