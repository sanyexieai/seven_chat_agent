//! 将 `codex exec --json` 的 JSONL 事件转为接近 Codex / Claude Code 终端的纯文本展示（降级用）。

use std::collections::HashMap;

use serde_json::Value;

use crate::cli_blocks::{cli_blocks_to_plain, parse_codex_exec_jsonl_to_blocks};

const LABEL_CODEX: &str = "▎ codex";
const LABEL_EXEC: &str = "▎ exec";
const LABEL_REASONING: &str = "▎ reasoning";

/// 流式解析：每行 JSONL 可能产生一段待追加到聊天气泡的增量文本。
#[derive(Debug, Default)]
pub struct CodexExecJsonlDisplayParser {
    has_content: bool,
    agent_emitted: HashMap<String, String>,
    commands: HashMap<String, CommandState>,
}

#[derive(Debug, Default)]
struct CommandState {
    command: String,
    header_emitted: bool,
    output_emitted_len: usize,
    finished: bool,
}

impl CodexExecJsonlDisplayParser {
    pub fn push_line(&mut self, line: &str) -> Option<String> {
        let line = line.trim();
        if line.is_empty() {
            return None;
        }
        let v: Value = serde_json::from_str(line).ok()?;
        match v.get("type")?.as_str()? {
            "item.started" => self.on_item_started(v.get("item")?),
            "item.completed" => self.on_item_completed(v.get("item")?),
            _ => None,
        }
    }

    fn on_item_started(&mut self, item: &Value) -> Option<String> {
        let id = item.get("id")?.as_str()?;
        let ty = item.get("type")?.as_str()?;
        if ty != "command_execution" {
            return None;
        }
        let status = item.get("status").and_then(|s| s.as_str()).unwrap_or("");
        if status != "in_progress" {
            return None;
        }
        let command = item.get("command")?.as_str()?.to_string();
        let st = self.commands.entry(id.to_string()).or_default();
        if st.header_emitted {
            return None;
        }
        st.command = command.clone();
        st.header_emitted = true;
        let body = format!("▶ {command}\n");
        Some(self.emit_section(LABEL_EXEC, &body))
    }

    fn on_item_completed(&mut self, item: &Value) -> Option<String> {
        let id = item.get("id")?.as_str()?;
        match item.get("type")?.as_str()? {
            "agent_message" => self.on_agent_message(id, item),
            "command_execution" => self.on_command_completed(id, item),
            "reasoning" => self.on_reasoning(id, item),
            other => self.on_generic_item(other, item),
        }
    }

    fn on_agent_message(&mut self, id: &str, item: &Value) -> Option<String> {
        let text = item.get("text")?.as_str()?;
        if text.is_empty() {
            return None;
        }
        let prev = self.agent_emitted.get(id).cloned().unwrap_or_default();
        let delta = if text.starts_with(&prev) {
            text[prev.len()..].to_string()
        } else {
            text.to_string()
        };
        if delta.is_empty() {
            return None;
        }
        let prev_empty = prev.is_empty();
        self.agent_emitted.insert(id.to_string(), text.to_string());
        if prev_empty {
            Some(self.emit_section(LABEL_CODEX, &delta))
        } else {
            Some(delta)
        }
    }

    fn on_command_completed(&mut self, id: &str, item: &Value) -> Option<String> {
        let command = item
            .get("command")
            .and_then(|c| c.as_str())
            .unwrap_or("");
        let output = item
            .get("aggregated_output")
            .and_then(|o| o.as_str())
            .unwrap_or("");
        let exit_code = item.get("exit_code");
        let status = item.get("status").and_then(|s| s.as_str()).unwrap_or("");

        let st = self.commands.entry(id.to_string()).or_default();
        if st.finished {
            return None;
        }
        st.finished = true;
        if !command.is_empty() {
            st.command = command.to_string();
        }

        let header_already = st.header_emitted;
        let mut body = String::new();
        if !header_already {
            if !st.command.is_empty() {
                body.push_str(&format!("▶ {}\n", st.command));
            }
            st.header_emitted = true;
        }

        if output.len() > st.output_emitted_len {
            let slice = &output[st.output_emitted_len..];
            st.output_emitted_len = output.len();
            body.push_str(&indent_block(slice));
        }

        if status == "completed" || exit_code.is_some() {
            body.push_str(&format_status_line(exit_code, status));
        }

        if body.is_empty() {
            return None;
        }

        if header_already {
            Some(self.prefix_gap() + &body)
        } else {
            Some(self.emit_section(LABEL_EXEC, &body))
        }
    }

    fn on_reasoning(&mut self, id: &str, item: &Value) -> Option<String> {
        let text = item
            .get("text")
            .or_else(|| item.get("summary"))
            .and_then(|t| t.as_str())
            .unwrap_or("");
        if text.is_empty() {
            return None;
        }
        let prev = self.agent_emitted.get(id).cloned().unwrap_or_default();
        let delta = if text.starts_with(&prev) {
            text[prev.len()..].to_string()
        } else {
            text.to_string()
        };
        if delta.is_empty() {
            return None;
        }
        let prev_empty = prev.is_empty();
        self.agent_emitted.insert(id.to_string(), text.to_string());
        if prev_empty {
            Some(self.emit_section(LABEL_REASONING, &delta))
        } else {
            Some(delta)
        }
    }

    fn on_generic_item(&mut self, ty: &str, item: &Value) -> Option<String> {
        let label = format!("▎ {ty}");
        if let Some(text) = item.get("text").and_then(|t| t.as_str()) {
            if !text.is_empty() {
                return Some(self.emit_section(&label, text));
            }
        }
        if let Some(cmd) = item.get("command").and_then(|c| c.as_str()) {
            return Some(self.emit_section(&label, &format!("▶ {cmd}\n")));
        }
        None
    }

    fn emit_section(&mut self, label: &str, body: &str) -> String {
        let gap = self.prefix_gap();
        self.has_content = true;
        format!("{gap}{label}\n{body}")
    }

    fn prefix_gap(&mut self) -> String {
        if self.has_content {
            "\n\n".to_string()
        } else {
            self.has_content = true;
            String::new()
        }
    }
}

fn indent_block(s: &str) -> String {
    let mut out = String::new();
    for line in s.lines() {
        if line.is_empty() {
            out.push('\n');
        } else {
            out.push_str("  ");
            out.push_str(line);
            out.push('\n');
        }
    }
    out
}

fn format_status_line(exit_code: Option<&Value>, status: &str) -> String {
    match exit_code.and_then(|c| c.as_i64()) {
        Some(0) => "✓ succeeded\n".to_string(),
        Some(code) => format!("✗ failed (exit {code})\n"),
        None if status == "completed" => "✓ succeeded\n".to_string(),
        None if status == "failed" => "✗ failed\n".to_string(),
        _ => String::new(),
    }
}

/// 将完整 stdout（多行 JSONL）折叠为聊天气泡用的展示文本。
pub fn parse_codex_exec_jsonl_to_display(buf: &[u8]) -> String {
    cli_blocks_to_plain(&parse_codex_exec_jsonl_to_blocks(buf))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn formats_agent_message_and_command_like_codex() {
        let lines = [
            r#"{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Planning."}}"#,
            r#"{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"/bin/bash -lc ls","status":"in_progress"}}"#,
            r#"{"type":"item.completed","item":{"id":"item_1","type":"command_execution","command":"/bin/bash -lc ls","aggregated_output":"a\nb\n","exit_code":0,"status":"completed"}}"#,
            r#"{"type":"item.completed","item":{"id":"item_2","type":"agent_message","text":"Done."}}"#,
        ];
        let mut p = CodexExecJsonlDisplayParser::default();
        let mut out = String::new();
        for line in lines {
            if let Some(d) = p.push_line(line) {
                out.push_str(&d);
            }
        }
        assert!(out.contains("▎ codex"));
        assert!(out.contains("Planning."));
        assert!(out.contains("▎ exec"));
        assert!(out.contains("/bin/bash -lc ls"));
        assert!(out.contains("  a"));
        assert!(out.contains("✓ succeeded"));
        assert!(out.contains("Done."));
    }

    #[test]
    fn parse_buffer_matches_streaming() {
        let buf = br#"{"type":"item.completed","item":{"id":"i0","type":"agent_message","text":"Hi"}}"#;
        assert_eq!(parse_codex_exec_jsonl_to_display(buf), "▎ codex\nHi");
    }
}
