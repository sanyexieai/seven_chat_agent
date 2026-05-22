use anyhow::{Context, Result};
use reqwest::Client;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Friend {
    pub id: String,
    pub name: String,
    pub avatar: Option<String>,
    pub system_prompt: String,
    pub personality: Option<String>,
    pub focus_tags: Vec<String>,
    pub backend_kind: String,
    pub backend_config: serde_json::Value,
    pub judge_provider_ref: Option<String>,
    pub enabled: bool,
    pub is_builtin: bool,
    pub created_at: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Conversation {
    pub id: String,
    pub kind: String,
    pub target_id: String,
    pub title: Option<String>,
    pub last_message_at: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Message {
    pub id: String,
    pub conversation_id: String,
    pub turn_id: String,
    pub parent_id: Option<String>,
    pub sender_kind: String,
    pub sender_id: String,
    pub sender_name: String,
    pub content: String,
    pub mentions: Vec<String>,
    pub status: String,
    pub model_used: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Provider {
    pub id: String,
    pub display_name: String,
    pub kind: String,
    pub base_url: String,
    pub default_model: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProviderKey {
    pub id: String,
    pub provider_id: String,
    pub label: String,
    pub status: String,
    pub current_spent_usd: f64,
}

#[derive(Clone)]
pub struct ApiClient {
    base: String,
    http: Client,
}

impl ApiClient {
    pub fn new(base: &str) -> Self {
        Self {
            base: base.trim_end_matches('/').to_string(),
            http: Client::builder().build().unwrap(),
        }
    }

    pub async fn list_friends(&self) -> Result<Vec<Friend>> {
        let url = format!("{}/api/friends", self.base);
        #[derive(Deserialize)]
        struct Resp {
            friends: Vec<Friend>,
        }
        let r: Resp = self
            .http
            .get(url)
            .send()
            .await?
            .json()
            .await
            .context("decode friends")?;
        Ok(r.friends)
    }

    pub async fn list_providers(&self) -> Result<Vec<Provider>> {
        #[derive(Deserialize)]
        struct Resp {
            providers: Vec<Provider>,
        }
        let r: Resp = self
            .http
            .get(format!("{}/api/providers", self.base))
            .send()
            .await?
            .json()
            .await?;
        Ok(r.providers)
    }

    pub async fn list_provider_keys(&self) -> Result<Vec<ProviderKey>> {
        #[derive(Deserialize)]
        struct Resp {
            provider_keys: Vec<ProviderKey>,
        }
        let r: Resp = self
            .http
            .get(format!("{}/api/provider_keys", self.base))
            .send()
            .await?
            .json()
            .await?;
        Ok(r.provider_keys)
    }

    pub async fn open_dm(&self, friend_id: &str) -> Result<(Conversation, Vec<Message>)> {
        #[derive(Deserialize)]
        struct Resp {
            conversation: Conversation,
            messages: Vec<Message>,
        }
        let r: Resp = self
            .http
            .get(format!("{}/api/conversations/dm/{friend_id}", self.base))
            .send()
            .await?
            .json()
            .await?;
        Ok((r.conversation, r.messages))
    }

    pub async fn send_dm(&self, friend_id: &str, content: &str) -> Result<()> {
        self.http
            .post(format!("{}/api/conversations/dm/{friend_id}", self.base))
            .json(&serde_json::json!({ "content": content }))
            .send()
            .await?;
        Ok(())
    }
}
