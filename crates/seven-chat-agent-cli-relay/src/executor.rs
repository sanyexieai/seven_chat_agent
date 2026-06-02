use anyhow::{Context, Result};
use seven_chat_agent_cli::{ensure_executable, exec_argv, CliLaunchConfig};
use seven_chat_agent_cli_relay_protocol::RelayMessage;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, BufReader};
use tokio::process::Command;

use crate::workspace;

pub async fn run_job_collect(
    job_id: &str,
    preset: &str,
    prompt: &str,
    friend_id: Option<&str>,
    group_id: Option<&str>,
    cwd_override: Option<&str>,
    cli_session_mode: Option<&str>,
    cli_session_id: Option<&str>,
    env: &[(String, String)],
) -> Vec<String> {
    match run_job_inner(
        job_id,
        preset,
        prompt,
        friend_id,
        group_id,
        cwd_override,
        cli_session_mode,
        cli_session_id,
        env,
    )
    .await
    {
        Ok(msgs) => msgs,
        Err(e) => {
            vec![RelayMessage::JobOutput {
                job_id: job_id.to_string(),
                text_delta: None,
                done: true,
                exit_code: Some(1),
                error: Some(e.to_string()),
            }
            .to_json()
            .unwrap_or_default()]
        }
    }
}

async fn run_job_inner(
    job_id: &str,
    preset: &str,
    prompt: &str,
    friend_id: Option<&str>,
    group_id: Option<&str>,
    cwd_override: Option<&str>,
    cli_session_mode: Option<&str>,
    cli_session_id: Option<&str>,
    env: &[(String, String)],
) -> Result<Vec<String>> {
    let cwd = if let Some(fid) = friend_id.filter(|s| !s.trim().is_empty()) {
        Some(
            workspace::resolve_job_cwd(fid, group_id, cwd_override)
                .context("resolve relay workspace")?
                .to_string_lossy()
                .into_owned(),
        )
    } else {
        cwd_override.map(str::to_string)
    };
    let cwd_ref = cwd.as_deref();
    let mut launch = CliLaunchConfig {
        preset: preset.to_string(),
        cmd: String::new(),
        cli_session_mode: cli_session_mode.map(str::to_string),
        cli_session_id: cli_session_id.map(str::to_string),
        cli_sandbox_mode: None,
    };
    let cmd = ensure_executable(preset, &launch).context("resolve cli executable")?;
    launch.cmd = cmd.clone();
    let mut args = exec_argv(preset, &launch, cwd_ref);
    args.push(prompt.to_string());

    let mut child = Command::new(&cmd);
    child.args(&args);
    if preset == seven_chat_agent_cli::PRESET_CURSOR {
        if let Ok(home) = std::env::var("HOME") {
            let local_bin = format!("{home}/.local/bin");
            let path = std::env::var("PATH").unwrap_or_default();
            child.env("PATH", format!("{local_bin}:{path}"));
        }
    }
    if let Some(c) = cwd_ref {
        child.current_dir(c);
    }
    for (k, v) in env {
        child.env(k, v);
    }
    child.stdin(std::process::Stdio::null());
    child.stdout(std::process::Stdio::piped());
    child.stderr(std::process::Stdio::piped());

    let mut child = child
        .spawn()
        .with_context(|| format!("spawn cli {cmd} (cwd={cwd_ref:?}, args={args:?})"))?;
    let stdout = child.stdout.take().context("stdout pipe")?;
    let stderr = child.stderr.take();
    let mut lines = BufReader::new(stdout).lines();

    let mut out = Vec::new();
    while let Some(line) = lines.next_line().await? {
        if line.is_empty() {
            continue;
        }
        out.push(
            RelayMessage::JobOutput {
                job_id: job_id.to_string(),
                text_delta: Some(format!("{line}\n")),
                done: false,
                exit_code: None,
                error: None,
            }
            .to_json()?,
        );
    }

    let status = child.wait().await?;
    if !status.success() {
        let mut err_detail = format!("cli exited with {:?}", status.code());
        if let Some(mut stderr) = stderr {
            let mut buf = String::new();
            if stderr.read_to_string(&mut buf).await.is_ok() {
                let t = buf.trim();
                if !t.is_empty() {
                    err_detail = format!("{err_detail}: {t}");
                }
            }
        }
        out.push(
            RelayMessage::JobOutput {
                job_id: job_id.to_string(),
                text_delta: None,
                done: true,
                exit_code: status.code(),
                error: Some(err_detail),
            }
            .to_json()?,
        );
        return Ok(out);
    }
    out.push(
        RelayMessage::JobOutput {
            job_id: job_id.to_string(),
            text_delta: None,
            done: true,
            exit_code: status.code(),
            error: None,
        }
        .to_json()?,
    );
    Ok(out)
}
