use crate::types::{GroupJudgeSettings, TriggerSenderKind};

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
}
