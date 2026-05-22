//! Honeycomb 群聊 **Judge**（是否接话）— 独立 crate，供 core / server / 前端配置序列化共用。

mod context;
mod engine;
mod heuristic;
mod member_override;
mod parse;
mod prompt;
mod resolve;
mod types;

pub use context::{HistoryLine, JudgeMember, JudgeRequest};
pub use engine::{JudgeEngine, LlmJudgeInput, LlmJudgePort};
pub use heuristic::evaluate as heuristic_evaluate;
pub use member_override::{resolve_effective_judge, MemberJudgeOverride};
pub use parse::{parse_lenient, parse_llm_response};
pub use prompt::{build_llm_prompt, LLM_JUDGE_SYSTEM};
pub use resolve::{resolve_llm_target, LlmJudgeTarget};
pub use types::{
    GroupJudgeSettings, HeuristicJudgeSettings, JudgeMode, Judgment, LlmJudgeSettings,
    TriggerSenderKind,
};
