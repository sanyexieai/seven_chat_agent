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
    /// 当前选中的 CLI / 记忆工作区。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub active_workspace_id: Option<String>,
    pub created_at: DateTime<Utc>,
}

/// 好友下的独立工作目录（多项目 / 多 Codex·Claude 会话）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Workspace {
    pub id: String,
    pub tenant_id: String,
    pub owner_friend_id: String,
    pub name: String,
    pub path: String,
    pub is_default: bool,
    pub cli_session_mode: Option<String>,
    pub cli_session_id: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// 工作区下的原生 CLI 会话（Codex thread / Claude session 等）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CliSession {
    pub id: String,
    pub tenant_id: String,
    pub workspace_id: String,
    pub tool: String,
    pub native_session_id: Option<String>,
    pub label: Option<String>,
    pub source_path: Option<String>,
    pub is_active: bool,
    pub last_used_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
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
    #[serde(default)]
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
    /// 外部 CLI 会话：`oneshot`（默认，每轮独立 exec）或 `resume`（Codex `exec resume` 续接）。
    #[serde(default)]
    pub cli_session_mode: Option<String>,
    /// `cli_session_mode=resume` 时的原生会话 ID（Codex thread / Cursor chat / Claude session）。
    #[serde(default, alias = "cli_thread_id")]
    pub cli_session_id: Option<String>,
    /// Codex 沙箱：`read-only` | `workspace-write` | `danger-full-access`（仅 `codex-exec`）。
    #[serde(default)]
    pub cli_sandbox_mode: Option<String>,
    /// 外部 CLI API Key 在 vault 中的引用（`vault:cli-auth-<friend_id>`）。
    #[serde(default)]
    pub cli_api_key_ref: Option<String>,
    /// 保存时一次性提交的 CLI API Key（仅 upsert 入参，不落库）。
    #[serde(default, skip_serializing)]
    pub cli_api_key: Option<String>,
    /// CLI 执行位置：`local`（服务端本机，默认）或 `relay`（经转发程序在远程本机执行）。
    #[serde(default)]
    pub execution_mode: Option<String>,
    /// `execution_mode=relay` 时绑定的转发节点 id（`relay_*`）。
    #[serde(default)]
    pub relay_id: Option<String>,
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

/// 去掉历史上内置 Provider 名称末尾的「(本地)」等后缀。
pub fn normalize_provider_display_name(name: &str) -> String {
    let n = name.trim();
    for suffix in [" (本地)", "（本地）", "(本地)"] {
        if let Some(stripped) = n.strip_suffix(suffix) {
            return stripped.trim().to_string();
        }
    }
    n.to_string()
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

pub use worker_bee_cli::{CliBlock, CliBlockDelta};

/// 新安装时内置 Hex 助理的稳定 id；旧库通过 `builtin_assistant_id()` 解析最早 builtin。
pub const BUILTIN_HEX_ASSISTANT_ID: &str = "builtin-hex-assistant";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum GroupMemberRole {
    #[default]
    Member,
    Assistant,
    Muted,
}

impl GroupMemberRole {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Member => "member",
            Self::Assistant => "assistant",
            Self::Muted => "muted",
        }
    }

    pub fn parse(s: &str) -> Self {
        match s {
            "assistant" => Self::Assistant,
            "muted" => Self::Muted,
            _ => Self::Member,
        }
    }

    pub fn participates_in_expert_scheduling(self) -> bool {
        matches!(self, Self::Member)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum AssistantMode {
    #[default]
    Delegate,
    Observe,
    Moderate,
}

/// 用户消息自治等级如何判定。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum AutonomyClassifier {
    #[default]
    Heuristic,
    /// 仅 LLM；失败则回退启发式。
    Auto,
    Llm,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssistantPolicyTemplate {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub settings: GroupAssistantSettings,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum AutonomyLevel {
    L0,
    #[default]
    L1,
    L2,
    L3,
    L4,
}

impl AutonomyLevel {
    pub fn rank(self) -> u8 {
        match self {
            Self::L0 => 0,
            Self::L1 => 1,
            Self::L2 => 2,
            Self::L3 => 3,
            Self::L4 => 4,
        }
    }
}

/// 群助理事件回写到外部 IM（Webhook）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssistantImWriteback {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub webhook_url: Option<String>,
    /// 入站 Webhook 校验密钥（与请求头 `X-SevenChatAgent-Im-Secret` 一致）。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub inbound_secret: Option<String>,
    #[serde(default = "default_true")]
    pub notify_delegate: bool,
    #[serde(default = "default_true")]
    pub notify_waiting_human: bool,
}

impl Default for AssistantImWriteback {
    fn default() -> Self {
        Self {
            enabled: false,
            webhook_url: None,
            inbound_secret: None,
            notify_delegate: true,
            notify_waiting_human: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupAssistantSettings {
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default)]
    pub mode: AssistantMode,
    #[serde(default)]
    pub max_autonomy: AutonomyLevel,
    #[serde(default = "default_true")]
    pub reply_after_experts: bool,
    /// 引用的策略模板 id（与内联字段合并后生效）。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub template_id: Option<String>,
    #[serde(default)]
    pub autonomy_classifier: AutonomyClassifier,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub classifier_provider_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub classifier_model: Option<String>,
    #[serde(default)]
    pub im_writeback: AssistantImWriteback,
    /// 超出拍板范围时，向前端/助理私聊/Todo 主动推送主人知悉（不阻断群内 Agent）。
    #[serde(default = "default_true")]
    pub notify_owner_proactively: bool,
}

impl Default for GroupAssistantSettings {
    fn default() -> Self {
        Self {
            enabled: true,
            mode: AssistantMode::Delegate,
            max_autonomy: AutonomyLevel::L2,
            reply_after_experts: true,
            template_id: None,
            autonomy_classifier: AutonomyClassifier::Heuristic,
            classifier_provider_id: None,
            classifier_model: None,
            im_writeback: AssistantImWriteback::default(),
            notify_owner_proactively: true,
        }
    }
}

/// 内置 Hex 助理的全局能力策略（跨私聊/群聊）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssistantGlobalSettings {
    /// 总开关：是否自动观察用户发言并写入记忆。
    #[serde(default = "default_true")]
    pub observe_enabled: bool,
    #[serde(default = "default_true")]
    pub observe_dm: bool,
    #[serde(default = "default_true")]
    pub observe_group: bool,
    /// 观察记忆正文截断长度（字符）。
    #[serde(default = "default_record_max_chars")]
    pub record_max_chars: u32,
    #[serde(default = "default_record_weight")]
    pub record_weight: f64,
    /// 观察/协助备忘：低于该字符数不写（过滤寒暄、空消息）。
    #[serde(default = "default_record_min_chars")]
    pub record_min_chars: u32,
    /// 过滤「你好/谢谢」等低信息量短句。
    #[serde(default = "default_true")]
    pub record_skip_low_signal: bool,
    /// 与助理私聊是否仍写「协助记录」流水账（默认关，靠提取/反思沉淀）。
    #[serde(default)]
    pub record_assist_memo: bool,
    /// 同一会话 scope 内，多少秒内相似观察不重复写入。
    #[serde(default = "default_observe_dedupe_secs")]
    pub observe_dedupe_secs: u32,
    /// 观察后是否周期性整理记忆。
    #[serde(default = "default_true")]
    pub auto_consolidate: bool,
    /// 每累计 N 条观察记忆触发一次整理。
    #[serde(default = "default_consolidate_every_n")]
    pub consolidate_every_n: u32,
    /// 定时/阈值触发时用 LLM 将 raw 合并为 curated。
    #[serde(default = "default_true")]
    pub auto_ingest_raw: bool,
    /// 单次 ingest 最多处理的 raw 条数。
    #[serde(default = "default_ingest_raw_batch_size")]
    pub ingest_raw_batch_size: u32,
    /// curated 层向量召回（需 OpenAI 兼容 embeddings API）。
    #[serde(default)]
    pub embedding_enabled: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub embedding_provider_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub embedding_model: Option<String>,
    /// ephemeral 作用域默认 TTL（小时）。
    #[serde(default = "default_ephemeral_ttl_hours")]
    pub ephemeral_ttl_hours: u32,
    /// 回合结束后反思 + 知识沉淀（reflections）。
    #[serde(default = "default_true")]
    pub evolution_enabled: bool,
    /// 回合结束后从对话提取长期记忆。
    #[serde(default = "default_true")]
    pub auto_extract_memories: bool,
    /// 助理主动处理（扫待办/做整理）总开关。
    #[serde(default = "default_true")]
    pub proactive_enabled: bool,
    /// 每轮最多自动处理多少条待办。
    #[serde(default = "default_proactive_batch")]
    pub proactive_batch_size: u32,
    /// 是否允许空闲守护把 Todo 调度给其他 agent 好友。
    #[serde(default)]
    pub proactive_delegate_enabled: bool,
    /// 允许被调度的 agent 好友 id 列表；空表示不限制（仍需打开 proactive_delegate_enabled）。
    #[serde(default)]
    pub proactive_delegate_friend_ids: Vec<String>,
    /// 助理月度 token 预算（0 表示不限制）。
    #[serde(default)]
    pub monthly_token_budget: u64,
    /// 助理当月已消耗 token（用于预算控制）。
    #[serde(default)]
    pub monthly_tokens_used: u64,
    /// 预算周期，格式 `YYYY-MM`。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub budget_period_ym: Option<String>,
    /// CLI 工具预设白名单；空列表表示不限制。
    #[serde(default)]
    pub tool_whitelist: Vec<String>,
    /// 服务端维护：距上次整理以来的观察条数。
    #[serde(default)]
    pub observe_streak: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub updated_at: Option<DateTime<Utc>>,
}

fn default_record_max_chars() -> u32 {
    500
}

fn default_record_weight() -> f64 {
    0.45
}

fn default_record_min_chars() -> u32 {
    20
}

fn default_observe_dedupe_secs() -> u32 {
    120
}

fn default_consolidate_every_n() -> u32 {
    10
}

fn default_ingest_raw_batch_size() -> u32 {
    25
}

fn default_ephemeral_ttl_hours() -> u32 {
    168
}

fn default_proactive_batch() -> u32 {
    2
}

impl Default for AssistantGlobalSettings {
    fn default() -> Self {
        Self {
            observe_enabled: true,
            observe_dm: true,
            observe_group: true,
            record_max_chars: default_record_max_chars(),
            record_weight: default_record_weight(),
            record_min_chars: default_record_min_chars(),
            record_skip_low_signal: true,
            record_assist_memo: false,
            observe_dedupe_secs: default_observe_dedupe_secs(),
            auto_consolidate: true,
            consolidate_every_n: default_consolidate_every_n(),
            auto_ingest_raw: true,
            ingest_raw_batch_size: default_ingest_raw_batch_size(),
            embedding_enabled: false,
            embedding_provider_id: None,
            embedding_model: None,
            ephemeral_ttl_hours: default_ephemeral_ttl_hours(),
            evolution_enabled: true,
            auto_extract_memories: true,
            proactive_enabled: true,
            proactive_batch_size: default_proactive_batch(),
            proactive_delegate_enabled: false,
            proactive_delegate_friend_ids: Vec::new(),
            monthly_token_budget: 0,
            monthly_tokens_used: 0,
            budget_period_ym: None,
            tool_whitelist: Vec::new(),
            observe_streak: 0,
            updated_at: None,
        }
    }
}

impl AssistantGlobalSettings {
    pub fn should_observe_dm(&self) -> bool {
        self.observe_enabled && self.observe_dm
    }

    pub fn should_observe_group(&self) -> bool {
        self.observe_enabled && self.observe_group
    }

    pub fn allows_cli_preset(&self, preset: &str) -> bool {
        if self.tool_whitelist.is_empty() {
            return true;
        }
        self.tool_whitelist
            .iter()
            .any(|p| p.eq_ignore_ascii_case(preset))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AssistantTodoStatus {
    Pending,
    Running,
    Done,
    Failed,
}

impl AssistantTodoStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Pending => "pending",
            Self::Running => "running",
            Self::Done => "done",
            Self::Failed => "failed",
        }
    }

    pub fn parse(s: &str) -> Self {
        match s {
            "running" => Self::Running,
            "done" => Self::Done,
            "failed" => Self::Failed,
            _ => Self::Pending,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssistantTodo {
    pub id: String,
    pub owner_friend_id: String,
    pub title: String,
    pub detail: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub repeat_rule: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub next_run_at: Option<DateTime<Utc>>,
    pub status: AssistantTodoStatus,
    pub priority: i64,
    pub source_turn_id: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl GroupAssistantSettings {
    /// 模板为底、群内联字段覆盖（非默认 classifier 等始终覆盖）。
    pub fn merge_with_template(&self, template: &GroupAssistantSettings) -> Self {
        let mut base = template.clone();
        base.template_id = self.template_id.clone();
        base.enabled = self.enabled;
        base.mode = self.mode;
        base.max_autonomy = self.max_autonomy;
        base.reply_after_experts = self.reply_after_experts;
        if self.autonomy_classifier != AutonomyClassifier::default() {
            base.autonomy_classifier = self.autonomy_classifier;
        }
        if self.classifier_provider_id.is_some() {
            base.classifier_provider_id = self.classifier_provider_id.clone();
        }
        if self.classifier_model.is_some() {
            base.classifier_model = self.classifier_model.clone();
        }
        if self.im_writeback.enabled
            || self.im_writeback.webhook_url.is_some()
            || self.im_writeback.inbound_secret.is_some()
        {
            base.im_writeback = self.im_writeback.clone();
        }
        base
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
    /// 群助理代用户发言时为 true。
    #[serde(default)]
    pub on_behalf_of_user: bool,
    pub content: String,
    /// Codex / 工蜂 CLI 的结构化块；`content` 为其纯文本降级副本，供搜索与旧客户端。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub content_blocks: Option<Vec<CliBlock>>,
    pub mentions: Vec<String>,
    pub status: MessageStatus,
    pub seen_by: Vec<String>,
    pub model_used: Option<String>,
    pub tokens_in: Option<i64>,
    pub tokens_out: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub workspace_id: Option<String>,
    /// 用户上传的附件（图片、文档等）。
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub attachments: Vec<MessageAttachment>,
    pub created_at: DateTime<Utc>,
}

/// 聊天消息附带的文件元数据（实体文件在 data/uploads 下）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MessageAttachment {
    pub id: String,
    pub filename: String,
    pub mime_type: String,
    pub size: u64,
    /// 相对 API 路径，如 `/api/uploads/{conversation_id}/{id}`。
    pub url: String,
}

/// 任务型群聊编排：竞选负责人 → 负责人执行（替代「接一句闲聊」）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GroupTaskFlowSettings {
    /// 开启后，用户消息走任务流（竞选 + 选举 + 负责人执行），不再全员 judge 接话。
    #[serde(default)]
    pub enabled: bool,
    /// 是否先让每位 Agent 竞选陈述优势（再选举）。
    #[serde(default = "default_true")]
    pub campaign_enabled: bool,
    /// 选举完成后仅负责人对用户任务做执行型回复（本轮不再 agent 接龙）。
    #[serde(default = "default_true")]
    pub leader_only_execute: bool,
    /// 负责人先发布结构化计划，再进入执行（不跑工具）。
    #[serde(default = "default_true")]
    pub plan_enabled: bool,
    /// 计划发布后，其他成员可简短评议（各 1 条，不抢执行）。
    #[serde(default = "default_true")]
    pub plan_review_enabled: bool,
    /// 竞选后成员互投（背书）负责人，与 LLM 选举合并计票。
    #[serde(default = "default_true")]
    pub peer_vote_enabled: bool,
    /// 用户 @ 成员或消息 mentions 含成员 id/名时，跳过竞选直接任命。
    #[serde(default = "default_true")]
    pub appoint_by_mention_enabled: bool,
}

fn default_true() -> bool {
    true
}

impl Default for GroupTaskFlowSettings {
    fn default() -> Self {
        Self {
            enabled: false,
            campaign_enabled: true,
            leader_only_execute: true,
            plan_enabled: true,
            plan_review_enabled: true,
            peer_vote_enabled: true,
            appoint_by_mention_enabled: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupSettings {
    /// 兼容旧数据；与 `judge.threshold` 同步。
    pub judge_threshold: f32,
    #[serde(default)]
    pub judge: seven_chat_agent_judge::GroupJudgeSettings,
    #[serde(default)]
    pub task_flow: GroupTaskFlowSettings,
    pub max_replies_per_turn: u32,
    pub per_agent_max_per_turn: u32,
    pub cooldown_ms: u64,
    pub human_priority: bool,
    pub human_pause_ms: u64,
    pub allow_agent_to_agent: bool,
    pub extra_system_prompt: Option<String>,
    /// 群聊共享 CLI 工作目录；留空则 `cli-workspaces/groups/<群ID>`。
    #[serde(default)]
    pub cli_workspace: Option<String>,
    #[serde(default)]
    pub assistant: GroupAssistantSettings,
}

impl Default for GroupSettings {
    fn default() -> Self {
        let judge = seven_chat_agent_judge::GroupJudgeSettings::default();
        Self {
            judge_threshold: judge.threshold,
            judge,
            task_flow: GroupTaskFlowSettings::default(),
            max_replies_per_turn: 8,
            per_agent_max_per_turn: 2,
            cooldown_ms: 4000,
            human_priority: true,
            human_pause_ms: 30_000,
            allow_agent_to_agent: true,
            extra_system_prompt: None,
            cli_workspace: None,
            assistant: GroupAssistantSettings::default(),
        }
    }
}

impl GroupSettings {
    pub fn effective_judge_threshold(&self) -> f32 {
        self.judge.effective_threshold(self.judge_threshold)
    }

    pub fn fallback_pick_top_enabled(&self) -> bool {
        self.judge.fallback_pick_top
    }

    pub fn sync_judge_threshold_fields(&mut self) {
        if self.judge.threshold <= 0.0 {
            self.judge.threshold = self.judge_threshold;
        }
        self.judge_threshold = self.judge.threshold;
    }
}

/// 群内某成员的 Judge 配置（按群定制，非好友全局）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupMemberConfig {
    pub friend_id: String,
    #[serde(default)]
    pub role: GroupMemberRole,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub judge_override: Option<seven_chat_agent_judge::MemberJudgeOverride>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Group {
    pub id: String,
    pub name: String,
    pub avatar: Option<String>,
    pub settings: GroupSettings,
    pub created_at: DateTime<Utc>,
}
