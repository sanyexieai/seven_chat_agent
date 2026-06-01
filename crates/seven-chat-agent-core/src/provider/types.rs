use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub role: String,
    /// OpenAI 兼容：字符串或 `[{type,text}|{type,image_url}]` 数组。
    pub content: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
}

impl ChatMessage {
    pub fn system(content: impl Into<String>) -> Self {
        Self {
            role: "system".into(),
            content: Value::String(content.into()),
            name: None,
        }
    }
    pub fn user(content: impl Into<String>) -> Self {
        Self {
            role: "user".into(),
            content: Value::String(content.into()),
            name: None,
        }
    }
    pub fn user_value(content: Value) -> Self {
        Self {
            role: "user".into(),
            content,
            name: None,
        }
    }
    pub fn assistant(content: impl Into<String>) -> Self {
        Self {
            role: "assistant".into(),
            content: Value::String(content.into()),
            name: None,
        }
    }
    pub fn text(&self) -> String {
        super::chat_content::chat_content_to_text(&self.content)
    }
}

#[derive(Debug, Clone)]
pub struct ChatRequest {
    pub model: String,
    pub api_key_id: Option<String>,
    pub messages: Vec<ChatMessage>,
    pub temperature: Option<f32>,
    pub top_p: Option<f32>,
    pub max_tokens: Option<u32>,
    pub stream: bool,
    pub response_format_json: bool,
}

impl ChatRequest {
    pub fn new(model: impl Into<String>, messages: Vec<ChatMessage>) -> Self {
        Self {
            model: model.into(),
            api_key_id: None,
            messages,
            temperature: None,
            top_p: None,
            max_tokens: None,
            stream: true,
            response_format_json: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProviderUsage {
    pub prompt_tokens: i64,
    pub completion_tokens: i64,
}

#[derive(Debug, Clone)]
pub enum ProviderEvent {
    Token(String),
    Thinking(String),
    Done {
        usage: ProviderUsage,
        finish_reason: Option<String>,
        model: String,
    },
}
