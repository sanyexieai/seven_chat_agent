//! 转发端 CLI 输出：Codex JSONL → 结构化 cli_delta；其它预设按纯文本。

use seven_chat_agent_cli::uses_codex_jsonl_stream;
use seven_chat_agent_cli_relay_protocol::RelayMessage;
use worker_bee_cli::{CliBlockDelta, CodexExecJsonlBlockParser};

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
    s.contains("Not inside a trusted directory")
        || s.contains("No such file or directory")
        || s.contains("error:")
        || s.contains("Error:")
        || s.contains("failed")
}

pub fn push_codex_line(
    job_id: &str,
    parser: &mut CodexExecJsonlBlockParser,
    line: &str,
    out: &mut Vec<String>,
) -> Result<(), serde_json::Error> {
    for delta in parser.push_line(line) {
        out.push(job_output_cli_delta(job_id, delta)?);
    }
    Ok(())
}

pub fn push_plain_text(job_id: &str, text: &str, out: &mut Vec<String>) -> Result<(), serde_json::Error> {
    if text.is_empty() {
        return Ok(());
    }
    out.push(
        RelayMessage::JobOutput {
            job_id: job_id.to_string(),
            text_delta: Some(text.to_string()),
            cli_delta: None,
            done: false,
            exit_code: None,
            error: None,
        }
        .to_json()?,
    );
    Ok(())
}

pub fn job_output_cli_delta(job_id: &str, delta: CliBlockDelta) -> Result<String, serde_json::Error> {
    RelayMessage::JobOutput {
        job_id: job_id.to_string(),
        text_delta: None,
        cli_delta: Some(serde_json::to_value(delta)?),
        done: false,
        exit_code: None,
        error: None,
    }
    .to_json()
}

pub fn uses_jsonl(preset: &str, args: &[String]) -> bool {
    uses_codex_jsonl_stream(preset) && args.iter().any(|a| a == "--json")
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
