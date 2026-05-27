//! Codex `exec --json` 结构化块与增量，供 honeycomb 前端原生渲染。

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CommandRunStatus {
    InProgress,
    Completed,
    Failed,
}

impl CommandRunStatus {
    fn from_codex(status: &str, exit_code: Option<i64>) -> Self {
        match exit_code {
            Some(0) => Self::Completed,
            Some(_) => Self::Failed,
            None if status == "completed" => Self::Completed,
            None if status == "failed" => Self::Failed,
            None if status == "in_progress" => Self::InProgress,
            _ => Self::InProgress,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::InProgress => "in_progress",
            Self::Completed => "completed",
            Self::Failed => "failed",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum CliBlock {
    AgentMessage {
        item_id: String,
        text: String,
    },
    CommandExecution {
        item_id: String,
        command: String,
        output: String,
        status: CommandRunStatus,
        exit_code: Option<i64>,
    },
    Reasoning {
        item_id: String,
        text: String,
    },
    Usage {
        input_tokens: u64,
        output_tokens: u64,
        cached_input_tokens: Option<u64>,
    },
    TodoList {
        item_id: String,
        items: Vec<TodoItem>,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TodoItem {
    pub text: String,
    pub completed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "op", rename_all = "snake_case")]
pub enum CliBlockDelta {
    AgentText {
        item_id: String,
        delta: String,
    },
    CommandStart {
        item_id: String,
        command: String,
    },
    CommandOutput {
        item_id: String,
        delta: String,
    },
    CommandFinish {
        item_id: String,
        exit_code: Option<i64>,
        status: String,
    },
    ReasoningText {
        item_id: String,
        delta: String,
    },
    Usage {
        input_tokens: u64,
        output_tokens: u64,
        cached_input_tokens: Option<u64>,
    },
    TodoListSet {
        item_id: String,
        items: Vec<TodoItem>,
    },
}

/// 将大块文本拆成多个增量，便于 WebSocket 流式推送（Codex `agent_message` 常在 completed 一次给出全文）。
pub fn stream_split_cli_delta(delta: CliBlockDelta, max_chars: usize) -> Vec<CliBlockDelta> {
    let max_chars = max_chars.max(8);
    match delta {
        CliBlockDelta::AgentText { item_id, delta } => {
            split_text_delta(item_id, delta, |id, d| CliBlockDelta::AgentText {
                item_id: id,
                delta: d,
            }, max_chars)
        }
        CliBlockDelta::ReasoningText { item_id, delta } => {
            split_text_delta(item_id, delta, |id, d| CliBlockDelta::ReasoningText {
                item_id: id,
                delta: d,
            }, max_chars)
        }
        other => vec![other],
    }
}

fn split_text_delta(
    item_id: String,
    text: String,
    mk: impl Fn(String, String) -> CliBlockDelta,
    max_chars: usize,
) -> Vec<CliBlockDelta> {
    if text.chars().count() <= max_chars {
        return vec![mk(item_id, text)];
    }
    let mut out = Vec::new();
    let mut chunk = String::new();
    let mut n = 0usize;
    for ch in text.chars() {
        chunk.push(ch);
        n += 1;
        if n >= max_chars {
            out.push(mk(item_id.clone(), chunk.clone()));
            chunk.clear();
            n = 0;
        }
    }
    if !chunk.is_empty() {
        out.push(mk(item_id, chunk));
    }
    out
}

pub fn apply_cli_block_delta(blocks: &mut Vec<CliBlock>, delta: &CliBlockDelta) {
    match delta {
        CliBlockDelta::AgentText { item_id, delta: text } => {
            if let Some(CliBlock::AgentMessage { text: t, .. }) =
                blocks.iter_mut().find(|b| matches!(b, CliBlock::AgentMessage { item_id: id, .. } if id == item_id))
            {
                t.push_str(text);
            } else {
                blocks.push(CliBlock::AgentMessage {
                    item_id: item_id.clone(),
                    text: text.clone(),
                });
            }
        }
        CliBlockDelta::CommandStart { item_id, command } => {
            if blocks
                .iter()
                .any(|b| matches!(b, CliBlock::CommandExecution { item_id: id, .. } if id == item_id))
            {
                return;
            }
            blocks.push(CliBlock::CommandExecution {
                item_id: item_id.clone(),
                command: command.clone(),
                output: String::new(),
                status: CommandRunStatus::InProgress,
                exit_code: None,
            });
        }
        CliBlockDelta::CommandOutput { item_id, delta: out } => {
            if let Some(CliBlock::CommandExecution { output, .. }) =
                blocks.iter_mut().find(|b| matches!(b, CliBlock::CommandExecution { item_id: id, .. } if id == item_id))
            {
                output.push_str(out);
            }
        }
        CliBlockDelta::CommandFinish {
            item_id,
            exit_code,
            status,
        } => {
            if let Some(CliBlock::CommandExecution {
                status: st,
                exit_code: ec,
                ..
            }) = blocks
                .iter_mut()
                .find(|b| matches!(b, CliBlock::CommandExecution { item_id: id, .. } if id == item_id))
            {
                *ec = *exit_code;
                *st = CommandRunStatus::from_codex(status, *exit_code);
            }
        }
        CliBlockDelta::ReasoningText { item_id, delta: text } => {
            if let Some(CliBlock::Reasoning { text: t, .. }) =
                blocks.iter_mut().find(|b| matches!(b, CliBlock::Reasoning { item_id: id, .. } if id == item_id))
            {
                t.push_str(text);
            } else {
                blocks.push(CliBlock::Reasoning {
                    item_id: item_id.clone(),
                    text: text.clone(),
                });
            }
        }
        CliBlockDelta::Usage {
            input_tokens,
            output_tokens,
            cached_input_tokens,
        } => {
            if let Some(CliBlock::Usage {
                input_tokens: i,
                output_tokens: o,
                cached_input_tokens: c,
            }) = blocks.iter_mut().find(|b| matches!(b, CliBlock::Usage { .. }))
            {
                *i = *input_tokens;
                *o = *output_tokens;
                *c = *cached_input_tokens;
            } else {
                blocks.push(CliBlock::Usage {
                    input_tokens: *input_tokens,
                    output_tokens: *output_tokens,
                    cached_input_tokens: *cached_input_tokens,
                });
            }
        }
        CliBlockDelta::TodoListSet { item_id, items } => {
            if let Some(CliBlock::TodoList { items: list, .. }) =
                blocks.iter_mut().find(|b| matches!(b, CliBlock::TodoList { item_id: id, .. } if id == item_id))
            {
                *list = items.clone();
            } else {
                blocks.push(CliBlock::TodoList {
                    item_id: item_id.clone(),
                    items: items.clone(),
                });
            }
        }
    }
}

/// 可搜索 / 降级的纯文本。
pub fn cli_blocks_to_plain(blocks: &[CliBlock]) -> String {
    let mut out = String::new();
    for b in blocks {
        let section = match b {
            CliBlock::AgentMessage { text, .. } => format!("▎ codex\n{text}"),
            CliBlock::CommandExecution {
                command,
                output,
                status,
                exit_code,
                ..
            } => {
                let mut s = format!("▎ exec\n▶ {command}\n");
                for line in output.lines() {
                    if line.is_empty() {
                        s.push('\n');
                    } else {
                        s.push_str("  ");
                        s.push_str(line);
                        s.push('\n');
                    }
                }
                match (status, exit_code) {
                    (CommandRunStatus::Completed, _) => s.push_str("✓ succeeded\n"),
                    (CommandRunStatus::Failed, Some(c)) => {
                        s.push_str(&format!("✗ failed (exit {c})\n"));
                    }
                    (CommandRunStatus::Failed, None) => s.push_str("✗ failed\n"),
                    (CommandRunStatus::InProgress, _) => {}
                }
                s
            }
            CliBlock::Reasoning { text, .. } => format!("▎ reasoning\n{text}"),
            CliBlock::Usage {
                input_tokens,
                output_tokens,
                cached_input_tokens,
            } => {
                let cached = cached_input_tokens
                    .map(|c| format!(", cached {c}"))
                    .unwrap_or_default();
                format!("▎ tokens\nin {input_tokens}, out {output_tokens}{cached}\n")
            }
            CliBlock::TodoList { items, .. } => {
                let mut s = String::from("▎ plan\n");
                for it in items {
                    let mark = if it.completed { "✓" } else { "○" };
                    s.push_str(&format!("{mark} {}\n", it.text));
                }
                s
            }
        };
        if !out.is_empty() && !section.is_empty() {
            out.push_str("\n\n");
        }
        out.push_str(&section);
    }
    out.trim().to_string()
}

pub fn parse_cli_blocks_json(s: &str) -> Option<Vec<CliBlock>> {
    if s.trim().is_empty() {
        return None;
    }
    serde_json::from_str(s).ok()
}

/// 流式解析 `codex exec --json` JSONL → 结构化增量。
#[derive(Debug, Default)]
pub struct CodexExecJsonlBlockParser {
    agent_emitted: HashMap<String, String>,
    commands: HashMap<String, CommandParseState>,
}

#[derive(Debug, Default)]
struct CommandParseState {
    command: String,
    output_emitted_len: usize,
    finished: bool,
}

impl CodexExecJsonlBlockParser {
    /// 单行 JSONL 可能产生多个增量（例如命令完成时：输出 + 结束状态）。
    pub fn push_line(&mut self, line: &str) -> Vec<CliBlockDelta> {
        let line = line.trim();
        if line.is_empty() {
            return vec![];
        }
        let Some(v) = serde_json::from_str::<Value>(line).ok() else {
            return vec![];
        };
        let Some(ty) = v.get("type").and_then(|t| t.as_str()) else {
            return vec![];
        };
        match ty {
            "item.started" => {
                if let Some(item) = v.get("item") {
                    if let Some(d) = self.on_item_started(item) {
                        return vec![d];
                    }
                }
                vec![]
            }
            "item.completed" => {
                if let Some(item) = v.get("item") {
                    return self.on_item_completed(item);
                }
                vec![]
            }
            "item.updated" => {
                if let Some(item) = v.get("item") {
                    return self.on_item_updated(item);
                }
                vec![]
            }
            "turn.completed" => self
                .on_turn_completed(&v)
                .map(|d| vec![d])
                .unwrap_or_default(),
            _ => vec![],
        }
    }

    fn on_item_started(&mut self, item: &Value) -> Option<CliBlockDelta> {
        let id = item.get("id")?.as_str()?.to_string();
        let ty = item.get("type")?.as_str()?;
        if ty == "todo_list" {
            return self.parse_todo_list_delta(&id, item);
        }
        if ty != "command_execution" {
            return None;
        }
        if item.get("status").and_then(|s| s.as_str()) != Some("in_progress") {
            return None;
        }
        let command = item.get("command")?.as_str()?.to_string();
        let st = self.commands.entry(id.clone()).or_default();
        if !st.command.is_empty() {
            return None;
        }
        st.command = command.clone();
        Some(CliBlockDelta::CommandStart { item_id: id, command })
    }

    fn on_item_completed(&mut self, item: &Value) -> Vec<CliBlockDelta> {
        let id = match item.get("id").and_then(|i| i.as_str()) {
            Some(s) => s.to_string(),
            None => return vec![],
        };
        match item.get("type").and_then(|t| t.as_str()) {
            Some("agent_message") => self.on_agent_message(&id, item).into_iter().collect(),
            Some("command_execution") => self.on_command_completed(&id, item),
            Some("reasoning") => self.on_reasoning(&id, item).into_iter().collect(),
            Some("todo_list") => self
                .parse_todo_list_delta(&id, item)
                .into_iter()
                .collect(),
            _ => vec![],
        }
    }

    fn on_item_updated(&mut self, item: &Value) -> Vec<CliBlockDelta> {
        let id = match item.get("id").and_then(|i| i.as_str()) {
            Some(s) => s.to_string(),
            None => return vec![],
        };
        match item.get("type").and_then(|t| t.as_str()) {
            Some("agent_message") => self.on_agent_message(&id, item).into_iter().collect(),
            Some("reasoning") => self.on_reasoning(&id, item).into_iter().collect(),
            Some("command_execution") => self.on_command_output_delta(&id, item).into_iter().collect(),
            Some("todo_list") => self
                .parse_todo_list_delta(&id, item)
                .into_iter()
                .collect(),
            _ => vec![],
        }
    }

    fn on_agent_message(&mut self, id: &str, item: &Value) -> Option<CliBlockDelta> {
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
        self.agent_emitted.insert(id.to_string(), text.to_string());
        Some(CliBlockDelta::AgentText {
            item_id: id.to_string(),
            delta,
        })
    }

    fn on_reasoning(&mut self, id: &str, item: &Value) -> Option<CliBlockDelta> {
        let text = item
            .get("text")
            .or_else(|| item.get("summary"))
            .and_then(|t| t.as_str())?;
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
        self.agent_emitted.insert(id.to_string(), text.to_string());
        Some(CliBlockDelta::ReasoningText {
            item_id: id.to_string(),
            delta,
        })
    }

    fn on_command_output_delta(&mut self, id: &str, item: &Value) -> Option<CliBlockDelta> {
        let output = item.get("aggregated_output").and_then(|o| o.as_str())?;
        let st = self.commands.entry(id.to_string()).or_default();
        if output.len() <= st.output_emitted_len {
            return None;
        }
        let slice = &output[st.output_emitted_len..];
        st.output_emitted_len = output.len();
        Some(CliBlockDelta::CommandOutput {
            item_id: id.to_string(),
            delta: slice.to_string(),
        })
    }

    fn parse_todo_list_delta(&mut self, id: &str, item: &Value) -> Option<CliBlockDelta> {
        let items = item.get("items")?.as_array()?;
        let parsed: Vec<TodoItem> = items
            .iter()
            .filter_map(|it| {
                Some(TodoItem {
                    text: it.get("text")?.as_str()?.to_string(),
                    completed: it.get("completed")?.as_bool()?,
                })
            })
            .collect();
        if parsed.is_empty() {
            return None;
        }
        Some(CliBlockDelta::TodoListSet {
            item_id: id.to_string(),
            items: parsed,
        })
    }

    fn on_command_completed(&mut self, id: &str, item: &Value) -> Vec<CliBlockDelta> {
        let command = item
            .get("command")
            .and_then(|c| c.as_str())
            .unwrap_or("");
        let output = item
            .get("aggregated_output")
            .and_then(|o| o.as_str())
            .unwrap_or("");
        let exit_code = item.get("exit_code").and_then(|c| c.as_i64());
        let status = item.get("status").and_then(|s| s.as_str()).unwrap_or("");

        let st = self.commands.entry(id.to_string()).or_default();
        if st.finished {
            return vec![];
        }

        let mut deltas = Vec::new();
        if !command.is_empty() && st.command.is_empty() {
            st.command = command.to_string();
            deltas.push(CliBlockDelta::CommandStart {
                item_id: id.to_string(),
                command: command.to_string(),
            });
        } else if !command.is_empty() {
            st.command = command.to_string();
        }

        if output.len() > st.output_emitted_len {
            let slice = &output[st.output_emitted_len..];
            st.output_emitted_len = output.len();
            if !slice.is_empty() {
                deltas.push(CliBlockDelta::CommandOutput {
                    item_id: id.to_string(),
                    delta: slice.to_string(),
                });
            }
        }

        if status == "completed" || exit_code.is_some() {
            st.finished = true;
            deltas.push(CliBlockDelta::CommandFinish {
                item_id: id.to_string(),
                exit_code,
                status: status.to_string(),
            });
        }

        deltas
    }

    fn on_turn_completed(&mut self, v: &Value) -> Option<CliBlockDelta> {
        let usage = v.get("usage")?;
        let input_tokens = usage.get("input_tokens")?.as_u64()?;
        let output_tokens = usage.get("output_tokens")?.as_u64()?;
        let cached_input_tokens = usage.get("cached_input_tokens").and_then(|c| c.as_u64());
        Some(CliBlockDelta::Usage {
            input_tokens,
            output_tokens,
            cached_input_tokens,
        })
    }
}

pub fn parse_codex_exec_jsonl_to_blocks(buf: &[u8]) -> Vec<CliBlock> {
    let s = String::from_utf8_lossy(buf);
    let mut parser = CodexExecJsonlBlockParser::default();
    let mut blocks = Vec::new();
    for line in s.lines() {
        for delta in parser.push_line(line) {
            apply_cli_block_delta(&mut blocks, &delta);
        }
    }
    blocks
}

/// 从 `codex exec --json` 输出中提取 `thread.started` 的 `thread_id`（用于 `exec resume`）。
pub fn parse_codex_thread_id_from_jsonl(buf: &[u8]) -> Option<String> {
    for line in String::from_utf8_lossy(buf).lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let Ok(v) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        if v.get("type").and_then(|t| t.as_str()) != Some("thread.started") {
            continue;
        }
        let id = v.get("thread_id").and_then(|t| t.as_str())?;
        if !id.is_empty() {
            return Some(id.to_string());
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stream_split_chunks_large_agent_text() {
        let deltas = stream_split_cli_delta(
            CliBlockDelta::AgentText {
                item_id: "a".into(),
                delta: "a".repeat(32),
            },
            8,
        );
        assert_eq!(deltas.len(), 4);
    }

    #[test]
    fn parses_thread_id_from_thread_started() {
        let buf = br#"{"type":"thread.started","thread_id":"019e683e-b8a4-7362-ab8d-b4a562db313b"}
{"type":"turn.started"}"#;
        assert_eq!(
            parse_codex_thread_id_from_jsonl(buf).as_deref(),
            Some("019e683e-b8a4-7362-ab8d-b4a562db313b")
        );
    }

    #[test]
    fn block_parser_builds_agent_and_command() {
        let lines = [
            r#"{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Plan"}}"#,
            r#"{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"ls","status":"in_progress"}}"#,
            r#"{"type":"item.completed","item":{"id":"item_1","type":"command_execution","command":"ls","aggregated_output":"a\n","exit_code":0,"status":"completed"}}"#,
            r#"{"type":"item.completed","item":{"id":"item_2","type":"agent_message","text":"Done"}}"#,
        ];
        let mut blocks = Vec::new();
        let mut p = CodexExecJsonlBlockParser::default();
        for line in lines {
            for d in p.push_line(line) {
                apply_cli_block_delta(&mut blocks, &d);
            }
        }
        assert_eq!(blocks.len(), 3);
        assert!(matches!(blocks[0], CliBlock::AgentMessage { .. }));
        assert!(matches!(blocks[1], CliBlock::CommandExecution { .. }));
        assert!(matches!(blocks[2], CliBlock::AgentMessage { .. }));
        let plain = cli_blocks_to_plain(&blocks);
        assert!(plain.contains("Plan"));
        assert!(plain.contains("ls"));
    }
}
