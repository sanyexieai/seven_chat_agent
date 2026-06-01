//! 聊天附件存储与多模态 LLM 内容构建。

use std::path::{Path, PathBuf};

use base64::{engine::general_purpose::STANDARD as B64, Engine};
use serde_json::{json, Value};
use uuid::Uuid;

use crate::domain::MessageAttachment;
use crate::{Error, Result};

const DEFAULT_MAX_BYTES: usize = 10 * 1024 * 1024;

pub fn uploads_root(data_dir: &str) -> PathBuf {
    Path::new(data_dir).join("uploads")
}

pub fn conversation_upload_dir(data_dir: &str, conversation_id: &str) -> PathBuf {
    uploads_root(data_dir).join(conversation_id)
}

fn max_upload_bytes() -> usize {
    std::env::var("SEVEN_CHAT_AGENT_UPLOAD_MAX_BYTES")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(DEFAULT_MAX_BYTES)
}

fn sanitize_filename(name: &str) -> String {
    let base = Path::new(name)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("file");
    let safe: String = base
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '.' || c == '-' || c == '_' {
                c
            } else {
                '_'
            }
        })
        .collect();
    if safe.is_empty() {
        "file".into()
    } else {
        safe.chars().take(120).collect()
    }
}

fn guess_mime(filename: &str, fallback: Option<&str>) -> String {
    if let Some(m) = fallback.filter(|s| !s.is_empty()) {
        return m.to_string();
    }
    mime_guess::from_path(filename)
        .first()
        .map(|m| m.essence_str().to_string())
        .unwrap_or_else(|| "application/octet-stream".to_string())
}

pub fn is_image_mime(mime: &str) -> bool {
    mime.starts_with("image/")
}

/// 保存上传字节，返回附件元数据。
pub fn save_upload(
    data_dir: &str,
    conversation_id: &str,
    filename: &str,
    mime_hint: Option<&str>,
    bytes: &[u8],
) -> Result<MessageAttachment> {
    if bytes.is_empty() {
        return Err(Error::bad_request("空文件"));
    }
    let max = max_upload_bytes();
    if bytes.len() > max {
        return Err(Error::bad_request(format!(
            "文件过大（最大 {} MB）",
            max / (1024 * 1024)
        )));
    }
    let id = Uuid::new_v4().to_string();
    let safe_name = sanitize_filename(filename);
    let mime_type = guess_mime(&safe_name, mime_hint);
    let dir = conversation_upload_dir(data_dir, conversation_id);
    std::fs::create_dir_all(&dir).map_err(Error::Io)?;
    let stored_name = format!("{id}_{safe_name}");
    let path = dir.join(&stored_name);
    std::fs::write(&path, bytes).map_err(Error::Io)?;
    let url = format!("/api/uploads/{conversation_id}/{id}");
    Ok(MessageAttachment {
        id,
        filename: safe_name,
        mime_type,
        size: bytes.len() as u64,
        url,
    })
}

pub fn attachment_disk_path(data_dir: &str, conversation_id: &str, attachment_id: &str) -> PathBuf {
    let dir = conversation_upload_dir(data_dir, conversation_id);
    if let Ok(entries) = std::fs::read_dir(&dir) {
        for ent in entries.flatten() {
            let name = ent.file_name();
            let name = name.to_string_lossy();
            if name.starts_with(&format!("{attachment_id}_")) {
                return ent.path();
            }
        }
    }
    dir.join(attachment_id)
}

pub fn read_attachment_bytes(data_dir: &str, conversation_id: &str, attachment_id: &str) -> Result<Vec<u8>> {
    let path = attachment_disk_path(data_dir, conversation_id, attachment_id);
    if !path.is_file() {
        return Err(Error::not_found("attachment file"));
    }
    std::fs::read(&path).map_err(Error::Io)
}

/// 发送前校验附件属于该会话且文件存在。
pub fn validate_attachments(
    data_dir: &str,
    conversation_id: &str,
    attachments: &[MessageAttachment],
) -> Result<()> {
    for a in attachments {
        let expected_url = format!("/api/uploads/{conversation_id}/{}", a.id);
        if a.url != expected_url {
            return Err(Error::bad_request("附件与会话不匹配"));
        }
        let path = attachment_disk_path(data_dir, conversation_id, &a.id);
        if !path.is_file() {
            return Err(Error::bad_request(format!("附件不存在: {}", a.filename)));
        }
    }
    Ok(())
}

pub fn content_with_attachments(text: &str, attachments: &[MessageAttachment]) -> String {
    let t = text.trim();
    if !t.is_empty() {
        return t.to_string();
    }
    if attachments.is_empty() {
        return String::new();
    }
    attachments
        .iter()
        .map(|a| format!("[附件: {}]", a.filename))
        .collect::<Vec<_>>()
        .join("\n")
}

/// 将文本 + 附件转为 OpenAI 兼容的 message content（字符串或 parts 数组）。
pub fn build_chat_content(
    data_dir: &str,
    conversation_id: &str,
    text: &str,
    attachments: &[MessageAttachment],
    vision: bool,
) -> Value {
    if attachments.is_empty() {
        return Value::String(text.to_string());
    }

    let mut parts: Vec<Value> = Vec::new();
    if !text.trim().is_empty() {
        parts.push(json!({"type": "text", "text": text}));
    }

    for a in attachments {
        if vision && is_image_mime(&a.mime_type) {
            if let Ok(bytes) = read_attachment_bytes(data_dir, conversation_id, &a.id) {
                let b64 = B64.encode(bytes);
                let url = format!("data:{};base64,{}", a.mime_type, b64);
                parts.push(json!({
                    "type": "image_url",
                    "image_url": { "url": url }
                }));
                continue;
            }
        }
        let note = if is_image_mime(&a.mime_type) {
            format!("[图片: {}]", a.filename)
        } else if a.mime_type.starts_with("text/")
            || a.filename.ends_with(".md")
            || a.filename.ends_with(".txt")
        {
            match read_attachment_bytes(data_dir, conversation_id, &a.id)
                .and_then(|b| String::from_utf8(b).map_err(|_| Error::bad_request("文本编码无效")))
            {
                Ok(body) => {
                    let clipped: String = body.chars().take(8000).collect();
                    format!("[文件 {}]\n{}", a.filename, clipped)
                }
                Err(_) => format!("[文件: {}]", a.filename),
            }
        } else {
            format!("[文件: {} ({}, {} bytes)]", a.filename, a.mime_type, a.size)
        };
        if let Some(last) = parts.last_mut() {
            if last.get("type") == Some(&Value::String("text".into())) {
                if let Some(t) = last.get_mut("text").and_then(|v| v.as_str()) {
                    let mut merged = t.to_string();
                    merged.push('\n');
                    merged.push_str(&note);
                    *last = json!({"type": "text", "text": merged});
                    continue;
                }
            }
        }
        parts.push(json!({"type": "text", "text": note}));
    }

    if parts.is_empty() {
        Value::String(text.to_string())
    } else if parts.len() == 1 {
        if let Some(t) = parts[0].get("text").and_then(|v| v.as_str()) {
            Value::String(t.to_string())
        } else {
            Value::Array(parts)
        }
    } else {
        Value::Array(parts)
    }
}
