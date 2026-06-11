use serde::{Deserialize, Serialize};

/// 本次 judge 实际走的通路（与群配置的 `JudgeMode` 可能不同，例如 LLM 失败或 Auto 回退）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum JudgeSource {
    Heuristic,
    Llm,
    /// 配置为 `llm` 但调用失败（未配 Provider、无 Key、解析失败等）。
    LlmFailed,
    /// `auto` 模式下 LLM 成功返回。
    AutoLlm,
    /// `auto` 模式下 LLM 未采用，回退启发式。
    AutoHeuristic,
}

impl JudgeSource {
    pub fn label_zh(self) -> &'static str {
        match self {
            Self::Heuristic => "启发式",
            Self::Llm => "LLM",
            Self::LlmFailed => "LLM 失败",
            Self::AutoLlm => "Auto→LLM",
            Self::AutoHeuristic => "Auto→启发式",
        }
    }
}

/// 单成员对「是否接话」的判断结果。
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Judgment {
    pub should_reply: bool,
    pub confidence: f32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default)]
    pub suggested_delay_ms: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<JudgeSource>,
}

/// Judge 运行模式（群级可配置）。
#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum JudgeMode {
    /// 仅启发式（快、无 API 成本）。
    #[default]
    Heuristic,
    /// 仅 LLM（需 Provider）。
    Llm,
    /// 优先 LLM，失败或未配置时回退启发式。
    Auto,
}

/// 启发式 judge 参数（群级可配置）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HeuristicJudgeSettings {
    pub user_confidence: f32,
    pub friend_confidence: f32,
    pub mention_confidence: f32,
    pub user_delay_ms: u64,
    pub friend_delay_ms: u64,
    pub mention_delay_ms: u64,
}

impl Default for HeuristicJudgeSettings {
    fn default() -> Self {
        Self {
            user_confidence: 0.72,
            friend_confidence: 0.58,
            mention_confidence: 0.92,
            user_delay_ms: 300,
            friend_delay_ms: 500,
            mention_delay_ms: 100,
        }
    }
}

/// LLM judge 参数（群级可配置；成员级 `judge_provider_ref` 可覆盖 Provider）。
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct LlmJudgeSettings {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provider_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub api_key_id: Option<String>,
}

/// 群聊 Judge 产品配置（存入 `GroupSettings.judge`）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GroupJudgeSettings {
    #[serde(default)]
    pub mode: JudgeMode,
    #[serde(default = "default_threshold")]
    pub threshold: f32,
    #[serde(default)]
    pub heuristic: HeuristicJudgeSettings,
    #[serde(default)]
    pub llm: LlmJudgeSettings,
    /// 全员未达阈值时，是否由调度器按最高分兜底 1 人（与 scheduler 协同）。
    #[serde(default = "default_true")]
    pub fallback_pick_top: bool,
}

fn default_threshold() -> f32 {
    0.55
}

fn default_true() -> bool {
    true
}

impl Default for GroupJudgeSettings {
    fn default() -> Self {
        Self {
            mode: JudgeMode::default(),
            threshold: default_threshold(),
            heuristic: HeuristicJudgeSettings::default(),
            llm: LlmJudgeSettings::default(),
            fallback_pick_top: true,
        }
    }
}

impl GroupJudgeSettings {
    pub fn effective_threshold(&self, legacy_threshold: f32) -> f32 {
        if self.threshold > 0.0 {
            self.threshold
        } else {
            legacy_threshold
        }
    }
}

/// 成员协作主动性（群聊调度用）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum InitiativeLevel {
    Proactive,
    #[default]
    Balanced,
    Passive,
}

impl InitiativeLevel {
    /// 调度排序权重：主动型优先接话。
    pub fn rank(self) -> u8 {
        match self {
            Self::Proactive => 2,
            Self::Balanced => 1,
            Self::Passive => 0,
        }
    }
}

/// 成员协调倾向。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum CoordinationLevel {
    Coordinator,
    Contributor,
    #[default]
    None,
}

/// 群聊调度行为提示（由成员画像推导或手填）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RoutingHints {
    #[serde(default)]
    pub initiative: InitiativeLevel,
    #[serde(default)]
    pub coordination: CoordinationLevel,
    #[serde(default = "default_true")]
    pub respond_to_mention: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub self_nominate: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub campaign_eligible: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fallback_pick_eligible: Option<bool>,
    #[serde(default = "default_true")]
    pub peer_vote_eligible: bool,
}

impl Default for RoutingHints {
    fn default() -> Self {
        Self {
            initiative: InitiativeLevel::Balanced,
            coordination: CoordinationLevel::None,
            respond_to_mention: true,
            self_nominate: None,
            campaign_eligible: None,
            fallback_pick_eligible: None,
            peer_vote_eligible: true,
        }
    }
}

impl RoutingHints {
    pub fn effective_self_nominate(&self) -> bool {
        self.self_nominate
            .unwrap_or(matches!(self.initiative, InitiativeLevel::Proactive))
    }

    pub fn effective_campaign_eligible(&self) -> bool {
        self.campaign_eligible
            .unwrap_or_else(|| self.effective_self_nominate())
    }

    pub fn effective_fallback_pick_eligible(&self) -> bool {
        self.fallback_pick_eligible.unwrap_or(!matches!(
            self.initiative,
            InitiativeLevel::Passive
        ))
    }
}

/// 触发消息发送方。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TriggerSenderKind {
    User,
    Friend,
    System,
}
