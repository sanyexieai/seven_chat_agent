//! Cursor `agent -p --output-format stream-json` JSONL 事件 → 结构化 CLI 增量。

use std::collections::HashMap;

use serde_json::Value;

use crate::cli_blocks::CliBlockDelta;

/// 流式解析 Cursor Agent `stream-json` 输出（配合 `--stream-partial-output`）。
#[derive(Debug, Default)]
pub struct CursorStreamJsonParser {
    assistant_text: HashMap<String, String>,
}

impl CursorStreamJsonParser {
    pub fn push_line(&mut self, line: &str) -> Vec<CliBlockDelta> {
        let line = line.trim();
        if line.is_empty() {
            return vec![];
        }
        let v: Value = match serde_json::from_str(line) {
            Ok(v) => v,
            Err(_) => return vec![],
        };
        match v.get("type").and_then(|t| t.as_str()) {
            Some("thinking") => self.on_thinking(&v),
            Some("assistant") => self.on_assistant(&v),
            Some("result") => self.on_result(&v),
            _ => vec![],
        }
    }

    fn on_thinking(&self, v: &Value) -> Vec<CliBlockDelta> {
        if v.get("subtype").and_then(|s| s.as_str()) != Some("delta") {
            return vec![];
        }
        let text = match v.get("text").and_then(|t| t.as_str()) {
            Some(t) if !t.is_empty() => t,
            _ => return vec![],
        };
        vec![CliBlockDelta::ReasoningText {
            item_id: session_item_id(v).to_string(),
            delta: text.to_string(),
        }]
    }

    fn on_assistant(&mut self, v: &Value) -> Vec<CliBlockDelta> {
        let Some(text) = extract_assistant_text(v) else {
            return vec![];
        };
        let sid = session_item_id(v).to_string();
        let prev = self.assistant_text.get(&sid).cloned().unwrap_or_default();
        if text == prev {
            return vec![];
        }

        let (delta, next) = if text.starts_with(&prev) {
            (text[prev.len()..].to_string(), text)
        } else {
            (text.clone(), format!("{prev}{text}"))
        };
        if delta.is_empty() {
            return vec![];
        }
        self.assistant_text.insert(sid.clone(), next);
        vec![CliBlockDelta::AgentText {
            item_id: sid,
            delta,
        }]
    }

    fn on_result(&self, v: &Value) -> Vec<CliBlockDelta> {
        let usage = match v.get("usage") {
            Some(u) => u,
            None => return vec![],
        };
        let input_tokens = usage
            .get("inputTokens")
            .and_then(|u| u.as_u64())
            .unwrap_or(0);
        let output_tokens = usage
            .get("outputTokens")
            .and_then(|u| u.as_u64())
            .unwrap_or(0);
        if input_tokens == 0 && output_tokens == 0 {
            return vec![];
        }
        vec![CliBlockDelta::Usage {
            input_tokens,
            output_tokens,
            cached_input_tokens: usage.get("cacheReadTokens").and_then(|u| u.as_u64()),
        }]
    }
}

fn session_item_id(v: &Value) -> &str {
    v.get("session_id")
        .and_then(|s| s.as_str())
        .unwrap_or("cursor")
}

fn extract_assistant_text(v: &Value) -> Option<String> {
    let content = v.get("message")?.get("content")?.as_array()?;
    let mut out = String::new();
    for part in content {
        if part.get("type").and_then(|t| t.as_str()) == Some("text") {
            if let Some(t) = part.get("text").and_then(|t| t.as_str()) {
                out.push_str(t);
            }
        }
    }
    if out.is_empty() {
        None
    } else {
        Some(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn partial_assistant_deltas_stream() {
        let mut p = CursorStreamJsonParser::default();
        let sid = "s1";
        let d1 = p.push_line(&format!(
            r#"{{"type":"assistant","message":{{"role":"assistant","content":[{{"type":"text","text":"你"}}]}},"session_id":"{sid}"}}"#
        ));
        assert_eq!(d1.len(), 1);
        assert!(matches!(
            &d1[0],
            CliBlockDelta::AgentText { delta, .. } if delta == "你"
        ));

        let d2 = p.push_line(&format!(
            r#"{{"type":"assistant","message":{{"role":"assistant","content":[{{"type":"text","text":"好"}}]}},"session_id":"{sid}"}}"#
        ));
        assert_eq!(d2.len(), 1);
        assert!(matches!(
            &d2[0],
            CliBlockDelta::AgentText { delta, .. } if delta == "好"
        ));
    }

    #[test]
    fn skips_duplicate_full_assistant_line() {
        let mut p = CursorStreamJsonParser::default();
        let line = r#"{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"你好"}]},"session_id":"s1"}"#;
        assert_eq!(p.push_line(line).len(), 1);
        assert!(p.push_line(line).is_empty());
    }

    #[test]
    fn thinking_delta_maps_to_reasoning() {
        let mut p = CursorStreamJsonParser::default();
        let deltas = p.push_line(
            r#"{"type":"thinking","subtype":"delta","text":"分析中","session_id":"s1"}"#,
        );
        assert!(matches!(
            deltas.as_slice(),
            [CliBlockDelta::ReasoningText { delta, .. }] if delta == "分析中"
        ));
    }

    #[test]
    fn result_usage_emitted_once() {
        let mut p = CursorStreamJsonParser::default();
        let line = r#"{"type":"result","subtype":"success","usage":{"inputTokens":10,"outputTokens":5,"cacheReadTokens":2},"session_id":"s1"}"#;
        let d = p.push_line(line);
        assert!(matches!(
            d.as_slice(),
            [CliBlockDelta::Usage {
                input_tokens: 10,
                output_tokens: 5,
                cached_input_tokens: Some(2),
            }]
        ));
    }
}
