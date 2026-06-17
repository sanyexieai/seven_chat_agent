use anyhow::{Context, Result};
use seven_chat_agent_cli::{ensure_executable, exec_argv, uses_codex_jsonl_stream, CliLaunchConfig};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, BufReader};
use tokio::process::Command;
use worker_bee_cli::{CodexExecJsonlBlockParser, CursorStreamJsonParser};

use crate::output::{
    ensure_codex_exec_cd, is_codex_exec_fatal_stderr, push_codex_line, push_cursor_line,
    push_job_done, push_plain_text, uses_codex_jsonl, uses_cursor_jsonl, JobOutputSink,
};
use crate::workspace;

/// 在本机执行 CLI，将 JobOutput 逐条写入 `out_tx`（真流式）。
pub async fn run_job(
    job_id: &str,
    preset: &str,
    prompt: &str,
    friend_id: Option<&str>,
    group_id: Option<&str>,
    cwd_override: Option<&str>,
    cli_session_mode: Option<&str>,
    cli_session_id: Option<&str>,
    env: &[(String, String)],
    out_tx: JobOutputSink,
) {
    if let Err(e) = run_job_inner(
        job_id,
        preset,
        prompt,
        friend_id,
        group_id,
        cwd_override,
        cli_session_mode,
        cli_session_id,
        env,
        &out_tx,
    )
    .await
    {
        let _ = push_job_done(job_id, Some(1), Some(e.to_string()), &out_tx);
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
    sink: &JobOutputSink,
) -> Result<()> {
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
    if uses_codex_jsonl_stream(preset) {
        if let Some(c) = cwd_ref {
            ensure_codex_exec_cd(&mut args, c);
        }
    }
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

    let codex_jsonl = uses_codex_jsonl(preset, &args);
    let cursor_jsonl = uses_cursor_jsonl(preset, &args);

    let mut child = child
        .spawn()
        .with_context(|| format!("spawn cli {cmd} (cwd={cwd_ref:?}, args={args:?})"))?;
    let stdout = child.stdout.take().context("stdout pipe")?;
    let stderr = child.stderr.take();
    let mut lines = BufReader::new(stdout).lines();

    let mut codex_parser = CodexExecJsonlBlockParser::default();
    let mut cursor_parser = CursorStreamJsonParser::default();

    while let Some(line) = lines.next_line().await? {
        if line.is_empty() {
            continue;
        }
        if codex_jsonl {
            push_codex_line(job_id, &mut codex_parser, line.trim(), sink)?;
        } else if cursor_jsonl {
            push_cursor_line(job_id, &mut cursor_parser, line.trim(), sink)?;
        } else {
            push_plain_text(job_id, &format!("{line}\n"), sink)?;
        }
    }

    let status = child.wait().await?;
    if let Some(mut stderr) = stderr {
        let mut buf = String::new();
        if stderr.read_to_string(&mut buf).await.is_ok() {
            let trimmed = buf.trim();
            if !trimmed.is_empty() {
                if codex_jsonl || cursor_jsonl {
                    if is_codex_exec_fatal_stderr(trimmed) {
                        let label = if cursor_jsonl { "Cursor Agent" } else { "Codex CLI" };
                        push_plain_text(
                            job_id,
                            &format!(
                                "\n（{label} 报错：{}）\n",
                                trimmed.lines().next().unwrap_or(trimmed)
                            ),
                            sink,
                        )?;
                    }
                } else {
                    push_plain_text(job_id, &format!("\n[stderr] {trimmed}\n"), sink)?;
                }
            }
        }
    }

    if !status.success() {
        let err_detail = format!("cli exited with {:?}", status.code());
        push_job_done(job_id, status.code(), Some(err_detail), sink)?;
        return Ok(());
    }
    push_job_done(job_id, status.code(), None, sink)?;
    Ok(())
}
