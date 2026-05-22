use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BackendKind {
    Pty,
    Api,
    Assistant,
    Human,
}

impl BackendKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            BackendKind::Pty => "pty",
            BackendKind::Api => "api",
            BackendKind::Assistant => "assistant",
            BackendKind::Human => "human",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "pty" => Some(BackendKind::Pty),
            "api" => Some(BackendKind::Api),
            "assistant" => Some(BackendKind::Assistant),
            "human" => Some(BackendKind::Human),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Friend {
    pub id: String,
    pub name: String,
    pub avatar: Option<String>,
    pub system_prompt: String,
    pub personality: Option<String>,
    pub focus_tags: Vec<String>,
    pub backend_kind: BackendKind,
    pub backend_config: serde_json::Value,
    pub judge_provider_ref: Option<String>,
    pub enabled: bool,
    pub is_builtin: bool,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ApiBackendConfig {
    pub provider_id: String,
    pub model: String,
    pub api_key_id: Option<String>,
    #[serde(default)]
    pub model_chain: Vec<ApiModelRef>,
    #[serde(default)]
    pub params: ApiSamplingParams,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiModelRef {
    pub provider_id: String,
    pub model: String,
    pub api_key_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ApiSamplingParams {
    pub temperature: Option<f32>,
    pub top_p: Option<f32>,
    pub max_tokens: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PtyBackendConfig {
    pub cmd: String,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default)]
    pub env: Vec<(String, String)>,
    pub cwd: Option<String>,
    pub ready_regex: Option<String>,
    pub response_start: Option<String>,
    pub response_end: Option<String>,
    pub idle_seconds: Option<u64>,
    pub preset: Option<String>,
    /// `preset=worker-bee-cli` 时：该工蜂实例使用的平台 API（非与 CLI 平级的「API 好友」）。
    #[serde(default)]
    pub provider_id: String,
    #[serde(default)]
    pub model: String,
    pub api_key_id: Option<String>,
    #[serde(default)]
    pub model_chain: Vec<ApiModelRef>,
    #[serde(default)]
    pub params: ApiSamplingParams,
    #[serde(default)]
    pub memory_top_k: Option<usize>,
    pub skills_dir: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct HumanBackendConfig {
    pub channel: String,
    pub endpoint: Option<String>,
    pub auth_token_ref: Option<String>,
    pub display_label: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AssistantBackendConfig {
    /// 推理方式：`provider`（默认）或 `cli`。
    #[serde(default)]
    pub inference: String,
    pub provider_id: String,
    pub model: String,
    pub api_key_id: Option<String>,
    #[serde(default = "default_skills_dir")]
    pub skills_dir: String,
    #[serde(default = "default_memory_top_k")]
    pub memory_top_k: usize,
    /// `inference=cli` 时的 Pty 预设（claude / codex-exec / worker-bee-cli …）。
    pub cli_preset: Option<String>,
    #[serde(default)]
    pub cmd: String,
    #[serde(default)]
    pub args: Vec<String>,
    pub cwd: Option<String>,
}

impl AssistantBackendConfig {
    pub fn uses_cli(&self) -> bool {
        self.inference == "cli"
    }
}

fn default_skills_dir() -> String {
    "data/skills".to_string()
}
fn default_memory_top_k() -> usize {
    5
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Provider {
    pub id: String,
    pub kind: String,
    pub display_name: String,
    pub base_url: String,
    pub default_model: Option<String>,
    pub capabilities: ProviderCapabilities,
    pub price: ProviderPrice,
    pub enabled: bool,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProviderCapabilities {
    #[serde(default)]
    pub stream: bool,
    #[serde(default)]
    pub tools: bool,
    #[serde(default)]
    pub vision: bool,
    #[serde(default)]
    pub thinking: bool,
    #[serde(default)]
    pub context_len: u32,
    #[serde(default)]
    pub embeddings: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProviderPrice {
    #[serde(default)]
    pub input_per_mtok: f64,
    #[serde(default)]
    pub output_per_mtok: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderKey {
    pub id: String,
    pub provider_id: String,
    pub label: String,
    pub secret_ref: String,
    pub rpm_limit: Option<i64>,
    pub tpm_limit: Option<i64>,
    pub monthly_budget_usd: Option<f64>,
    pub current_spent_usd: f64,
    pub status: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ConvKind {
    Dm,
    Group,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Conversation {
    pub id: String,
    pub kind: ConvKind,
    pub target_id: String,
    pub title: Option<String>,
    pub last_message_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SenderKind {
    User,
    Friend,
    System,
}

impl SenderKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            SenderKind::User => "user",
            SenderKind::Friend => "friend",
            SenderKind::System => "system",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "user" => Some(Self::User),
            "friend" => Some(Self::Friend),
            "system" => Some(Self::System),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MessageStatus {
    Pending,
    Streaming,
    Done,
    Failed,
    WaitingHuman,
}

impl MessageStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Pending => "pending",
            Self::Streaming => "streaming",
            Self::Done => "done",
            Self::Failed => "failed",
            Self::WaitingHuman => "waiting_human",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "pending" => Some(Self::Pending),
            "streaming" => Some(Self::Streaming),
            "done" => Some(Self::Done),
            "failed" => Some(Self::Failed),
            "waiting_human" => Some(Self::WaitingHuman),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub id: String,
    pub conversation_id: String,
    pub turn_id: String,
    pub parent_id: Option<String>,
    pub sender_kind: SenderKind,
    pub sender_id: String,
    pub sender_name: String,
    pub content: String,
    pub mentions: Vec<String>,
    pub status: MessageStatus,
    pub seen_by: Vec<String>,
    pub model_used: Option<String>,
    pub tokens_in: Option<i64>,
    pub tokens_out: Option<i64>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupSettings {
    pub judge_threshold: f32,
    pub max_replies_per_turn: u32,
    pub per_agent_max_per_turn: u32,
    pub cooldown_ms: u64,
    pub human_priority: bool,
    pub human_pause_ms: u64,
    pub allow_agent_to_agent: bool,
    pub extra_system_prompt: Option<String>,
}

impl Default for GroupSettings {
    fn default() -> Self {
        Self {
            judge_threshold: 0.55,
            max_replies_per_turn: 8,
            per_agent_max_per_turn: 2,
            cooldown_ms: 4000,
            human_priority: true,
            human_pause_ms: 30_000,
            allow_agent_to_agent: true,
            extra_system_prompt: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Group {
    pub id: String,
    pub name: String,
    pub avatar: Option<String>,
    pub settings: GroupSettings,
    pub created_at: DateTime<Utc>,
}
