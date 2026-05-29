//! 对接 `seven-chat-agent-judge` crate 与 Provider 层。

mod bridge;
mod service;

pub use bridge::ProviderLlmJudgePort;
pub use seven_chat_agent_judge::{
    resolve_effective_judge, resolve_llm_target, GroupJudgeSettings, HeuristicJudgeSettings,
    JudgeEngine, JudgeMember, JudgeMode, JudgeRequest, JudgeSource, Judgment, LlmJudgeSettings,
    MemberJudgeOverride, TriggerSenderKind,
};
pub use service::JudgeService;
