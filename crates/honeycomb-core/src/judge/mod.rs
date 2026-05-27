//! 对接 `honeycomb-judge` crate 与 Provider 层。

mod bridge;
mod service;

pub use bridge::ProviderLlmJudgePort;
pub use honeycomb_judge::{
    resolve_effective_judge, resolve_llm_target, GroupJudgeSettings, HeuristicJudgeSettings,
    JudgeEngine, JudgeMember, JudgeMode, JudgeRequest, JudgeSource, Judgment, LlmJudgeSettings,
    MemberJudgeOverride, TriggerSenderKind,
};
pub use service::JudgeService;
