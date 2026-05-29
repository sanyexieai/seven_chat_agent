use anyhow::{Context, Result};
use seven_chat_agent_cli::{ensure_executable, exec_argv, CliLaunchConfig};
use seven_chat_agent_cli_relay_protocol::RelayMessage;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

pub async fn run_job_collect(
    job_id: &str,
    preset: &str,
    prompt: &str,
    cwd: Option<&str>,
    cli_session_mode: Option<&str>,
    cli_session_id: Option<&str>,
    env: &[(String, String)],
) -> Vec<String> {
    match run_job_inner(
        job_id,
        preset,
        prompt,
        cwd,
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
    cwd: Option<&str>,
    cli_session_mode: Option<&str>,
    cli_session_id: Option<&str>,
    env: &[(String, String)],
) -> Result<Vec<String>> {
    let mut launch = CliLaunchConfig {
        preset: preset.to_string(),
        cmd: String::new(),
        cli_session_mode: cli_session_mode.map(str::to_string),
        cli_session_id: cli_session_id.map(str::to_string),
        cli_sandbox_mode: None,
    };
    let cmd = ensure_executable(preset, &launch).context("unknown cli preset")?;
    launch.cmd = cmd;
    let mut argv = exec_argv(preset, &launch, cwd);
    argv.push(prompt.to_string());

    let mut child = Command::new(&argv[0]);
    if argv.len() > 1 {
        child.args(&argv[1..]);
    }
    if let Some(c) = cwd {
        child.current_dir(c);
    }
    for (k, v) in env {
        child.env(k, v);
    }
    child.stdin(std::process::Stdio::null());
    child.stdout(std::process::Stdio::piped());
    child.stderr(std::process::Stdio::piped());

    let mut child = child.spawn().context("spawn cli")?;
    let stdout = child.stdout.take().context("stdout pipe")?;
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
    out.push(
        RelayMessage::JobOutput {
            job_id: job_id.to_string(),
            text_delta: None,
            done: true,
            exit_code: status.code(),
            error: if status.success() {
                None
            } else {
                Some(format!("cli exited with {:?}", status.code()))
            },
        }
        .to_json()?,
    );
    Ok(out)
}
