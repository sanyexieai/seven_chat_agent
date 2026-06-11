use crate::types::{GroupJudgeSettings, RoutingHints, TriggerSenderKind};

/// 单条历史消息摘要（与存储层解耦）。
#[derive(Debug, Clone)]
pub struct HistoryLine {
    pub sender_name: String,
    pub content: String,
}

/// 待判断成员视角。
#[derive(Debug, Clone)]
pub struct JudgeMember {
    pub id: String,
    pub name: String,
    pub personality: Option<String>,
    pub focus_tags: Vec<String>,
    /// 成员级 judge Provider（好友 `judge_provider_ref`）。
    pub judge_provider_ref: Option<String>,
}

/// 一次 judge 请求的完整上下文。
#[derive(Debug, Clone)]
pub struct JudgeRequest {
    pub group_judge: GroupJudgeSettings,
    pub member: JudgeMember,
    pub trigger_sender: TriggerSenderKind,
    pub trigger_sender_id: String,
    pub trigger_sender_name: String,
    pub trigger_content: String,
    pub mentions: Vec<String>,
    pub history: Vec<HistoryLine>,
    pub extra_group_prompt: Option<String>,
    /// 成员画像推导的协作行为；`None` 时与改造前一致。
    pub routing_hints: Option<RoutingHints>,
    /// 注入 LLM judge 的人格描述块。
    pub persona_block: Option<String>,
    /// 群共识摘录（C 层，≤200 字），含失败记录与分工要点。
    pub group_context_excerpt: Option<String>,
}
