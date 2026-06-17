//! 转发端 CLI 输出：Codex JSONL → 结构化 cli_delta；其它预设按纯文本。

use seven_chat_agent_cli::{uses_codex_jsonl_stream, uses_cursor_stream_json};
use seven_chat_agent_cli_relay_protocol::RelayMessage;
use tokio::sync::mpsc;
use worker_bee_cli::{CliBlockDelta, CodexExecJsonlBlockParser, CursorStreamJsonParser};

pub type JobOutputSink = mpsc::UnboundedSender<String>;

/// codex exec 除进程 `current_dir` 外还支持 `-C` 指定 agent 工作根目录。
pub fn ensure_codex_exec_cd(args: &mut Vec<String>, cwd: &str) {
    let mut i = 0;
    while i < args.len() {
        if args[i] == "-C" || args[i] == "--cd" {
            if i + 1 < args.len() {
                args[i + 1] = cwd.to_string();
            }
            return;
        }
        i += 1;
    }
    let insert_at = args.iter().position(|a| a == "exec").map(|p| p + 1).unwrap_or(0);
    args.insert(insert_at, cwd.to_string());
    args.insert(insert_at, "-C".into());
}

pub fn is_codex_exec_fatal_stderr(s: &str) -> bool {
    worker_bee_cli::is_cli_fatal_stderr(s)
}

fn emit(sink: &JobOutputSink, msg: RelayMessage) -> Result<(), serde_json::Error> {
    if let Ok(json) = msg.to_json() {
        let _ = sink.send(json);
    }
    Ok(())
}

pub fn push_codex_line(
    job_id: &str,
    parser: &mut CodexExecJsonlBlockParser,
    line: &str,
    sink: &JobOutputSink,
) -> Result<(), serde_json::Error> {
    for delta in parser.push_line(line) {
        emit(sink, job_output_cli_delta(job_id, delta)?)?;
    }
    Ok(())
}

pub fn push_cursor_line(
    job_id: &str,
    parser: &mut CursorStreamJsonParser,
    line: &str,
    sink: &JobOutputSink,
) -> Result<(), serde_json::Error> {
    for delta in parser.push_line(line) {
        emit(sink, job_output_cli_delta(job_id, delta)?)?;
    }
    Ok(())
}

pub fn push_plain_text(job_id: &str, text: &str, sink: &JobOutputSink) -> Result<(), serde_json::Error> {
    if text.is_empty() {
        return Ok(());
    }
    emit(
        sink,
        RelayMessage::JobOutput {
            job_id: job_id.to_string(),
            text_delta: Some(text.to_string()),
            cli_delta: None,
            done: false,
            exit_code: None,
            error: None,
        },
    )
}

pub fn job_output_cli_delta(job_id: &str, delta: CliBlockDelta) -> Result<RelayMessage, serde_json::Error> {
    Ok(RelayMessage::JobOutput {
        job_id: job_id.to_string(),
        text_delta: None,
        cli_delta: Some(serde_json::to_value(delta)?),
        done: false,
        exit_code: None,
        error: None,
    })
}

pub fn push_job_done(
    job_id: &str,
    exit_code: Option<i32>,
    error: Option<String>,
    sink: &JobOutputSink,
) -> Result<(), serde_json::Error> {
    emit(
        sink,
        RelayMessage::JobOutput {
            job_id: job_id.to_string(),
            text_delta: None,
            cli_delta: None,
            done: true,
            exit_code,
            error,
        },
    )
}

pub fn uses_codex_jsonl(preset: &str, args: &[String]) -> bool {
    uses_codex_jsonl_stream(preset) && args.iter().any(|a| a == "--json")
}

pub fn uses_cursor_jsonl(preset: &str, args: &[String]) -> bool {
    uses_cursor_stream_json(preset) && args.iter().any(|a| a == "stream-json")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inserts_codex_cd_flag() {
        let mut args = vec!["exec".into(), "--json".into()];
        ensure_codex_exec_cd(&mut args, "/tmp/ws");
        assert!(args.windows(2).any(|w| w[0] == "-C" && w[1] == "/tmp/ws"));
    }
}
