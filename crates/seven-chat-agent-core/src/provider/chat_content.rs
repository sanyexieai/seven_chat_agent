use serde_json::Value;

/// 将 Chat API 的 content（字符串或多模态数组）转为纯文本。
pub fn chat_content_to_text(content: &Value) -> String {
    match content {
        Value::String(s) => s.clone(),
        Value::Array(parts) => {
            let mut out = String::new();
            for p in parts {
                match p.get("type").and_then(|t| t.as_str()) {
                    Some("text") => {
                        if let Some(t) = p.get("text").and_then(|v| v.as_str()) {
                            if !out.is_empty() {
                                out.push('\n');
                            }
                            out.push_str(t);
                        }
                    }
                    Some("image_url") => {
                        if !out.is_empty() {
                            out.push('\n');
                        }
                        out.push_str("[图片]");
                    }
                    _ => {}
                }
            }
            out
        }
        _ => content.to_string(),
    }
}
