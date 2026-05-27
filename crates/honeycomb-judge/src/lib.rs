//! Honeycomb 群聊 **Judge**（是否接话）— 独立 crate，供 core / server / 前端配置序列化共用。

mod context;
mod election;
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
pub use election::{
    build_election_prompt, build_peer_vote_prompt, format_peer_vote_tally, parse_election_response,
    parse_peer_vote_response, tally_peer_votes, ElectionRaw, PeerVoteRaw, ELECTION_SYSTEM,
    PEER_VOTE_SYSTEM,
};
pub use prompt::{build_llm_prompt, LLM_JUDGE_SYSTEM};
pub use resolve::{resolve_llm_target, LlmJudgeTarget};
pub use types::{
    GroupJudgeSettings, HeuristicJudgeSettings, JudgeMode, JudgeSource, Judgment,
    LlmJudgeSettings, TriggerSenderKind,
};
