use std::path::Path;
use std::process::Stdio;

use tokio::process::Command;

use super::config::SourceCenterConfig;
use super::layout::{workspace_dir_name, EvolutionLayout};
use super::run_log::EvolutionStepLog;
use crate::{Error, Result};

pub struct SyncSourceResult {
    pub workspace_dir: String,
    pub commit: Option<String>,
    pub step: EvolutionStepLog,
}

pub async fn sync_source(
    layout: &EvolutionLayout,
    source: &SourceCenterConfig,
) -> Result<SyncSourceResult> {
    let ws_name = workspace_dir_name(&source.id, &source.workspace_dir);
    let ws_path = layout.workspace_path(&ws_name);
    layout.ensure_dirs()?;

    let step = if ws_path.join(".git").exists() {
        fetch_and_checkout(&ws_path, &source.branch).await?
    } else {
        clone_repo(
            &source.remote_url,
            &ws_path,
            &source.branch,
            source.shallow_depth,
        )
        .await?
    };

    let commit = read_head_commit(&ws_path).await.ok();
    Ok(SyncSourceResult {
        workspace_dir: ws_name,
        commit,
        step,
    })
}

async fn clone_repo(
    remote_url: &str,
    dest: &Path,
    branch: &str,
    shallow_depth: u32,
) -> Result<EvolutionStepLog> {
    if remote_url.trim().is_empty() {
        return Err(Error::bad_request("source.remote_url 未配置"));
    }
    if let Some(parent) = dest.parent() {
        tokio::fs::create_dir_all(parent)
            .await
            .map_err(|e| Error::Config(e.to_string()))?;
    }
    let mut cmd = Command::new("git");
    cmd.arg("clone");
    if shallow_depth > 0 {
        cmd.arg("--depth").arg(shallow_depth.to_string());
    }
    cmd.arg("--branch").arg(branch);
    cmd.arg(remote_url);
    cmd.arg(dest);
    run_git_step("git_clone", cmd).await
}

async fn fetch_and_checkout(ws_path: &Path, branch: &str) -> Result<EvolutionStepLog> {
    let fetch = Command::new("git")
        .current_dir(ws_path)
        .args(["fetch", "origin", branch])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await
        .map_err(|e| Error::Config(format!("git fetch: {e}")))?;
    let checkout = Command::new("git")
        .current_dir(ws_path)
        .args(["checkout", branch])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await
        .map_err(|e| Error::Config(format!("git checkout: {e}")))?;
    let pull = Command::new("git")
        .current_dir(ws_path)
        .args(["pull", "--ff-only", "origin", branch])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await
        .map_err(|e| Error::Config(format!("git pull: {e}")))?;
    let ok = fetch.status.success() && checkout.status.success() && pull.status.success();
    let stdout = format!(
        "fetch:\n{}\ncheckout:\n{}\npull:\n{}",
        String::from_utf8_lossy(&fetch.stdout),
        String::from_utf8_lossy(&checkout.stdout),
        String::from_utf8_lossy(&pull.stdout),
    );
    let stderr = format!(
        "{}{}{}",
        String::from_utf8_lossy(&fetch.stderr),
        String::from_utf8_lossy(&checkout.stderr),
        String::from_utf8_lossy(&pull.stderr),
    );
    Ok(EvolutionStepLog {
        name: "git_sync".into(),
        ok,
        detail: if ok {
            format!("已同步分支 {branch}")
        } else {
            "git fetch/checkout/pull 失败".into()
        },
        stdout,
        stderr,
    })
}

async fn read_head_commit(ws_path: &Path) -> Result<String> {
    let out = Command::new("git")
        .current_dir(ws_path)
        .args(["rev-parse", "HEAD"])
        .output()
        .await
        .map_err(|e| Error::Config(e.to_string()))?;
    if !out.status.success() {
        return Err(Error::Config("git rev-parse 失败".into()));
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

async fn run_git_step(name: &str, mut cmd: Command) -> Result<EvolutionStepLog> {
    let out = cmd
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await
        .map_err(|e| Error::Config(format!("{name}: {e}")))?;
    Ok(EvolutionStepLog {
        name: name.into(),
        ok: out.status.success(),
        detail: if out.status.success() {
            "成功".into()
        } else {
            format!("退出码 {:?}", out.status.code())
        },
        stdout: String::from_utf8_lossy(&out.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&out.stderr).into_owned(),
    })
}
