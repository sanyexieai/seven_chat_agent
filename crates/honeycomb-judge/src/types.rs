use serde::{Deserialize, Serialize};

/// 单成员对「是否接话」的判断结果。
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Judgment {
    pub should_reply: bool,
    pub confidence: f32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default)]
    pub suggested_delay_ms: u64,
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

/// 触发消息发送方。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TriggerSenderKind {
    User,
    Friend,
    System,
}
