//! SevenChatAgent 群聊 **Judge**（是否接话）— 独立 crate，供 core / server / 前端配置序列化共用。

mod context;
mod delegate_resume;
mod delivery;
mod election;
mod engine;
mod heuristic;
mod member_override;
mod parse;
mod prompt;
mod redundancy;
mod resolve;
mod types;

pub use context::{HistoryLine, JudgeMember, JudgeRequest};
pub use engine::{JudgeEngine, LlmJudgeInput, LlmJudgePort};
pub use heuristic::evaluate as heuristic_evaluate;
pub use member_override::{resolve_effective_judge, MemberJudgeOverride};
pub use parse::{parse_lenient, parse_llm_response};
pub use delegate_resume::{
    build_delegate_resume_prompt, heuristic_delegate_resume, parse_delegate_resume_response,
    DelegateResumeRaw, DELEGATE_RESUME_SYSTEM,
};
pub use delivery::{
    build_delivery_check_prompt, build_stagnation_check_prompt, heuristic_delivery_check,
    heuristic_stagnation_check, parse_delivery_check_response, parse_stagnation_check_response,
    DeliveryCheckRaw, StagnationCheckRaw, DELIVERY_CHECK_SYSTEM, STAGNATION_CHECK_SYSTEM,
};
pub use election::{
    build_election_prompt, build_peer_vote_prompt, format_peer_vote_tally, parse_election_response,
    parse_peer_vote_response, tally_peer_votes, ElectionRaw, PeerVoteRaw, ELECTION_SYSTEM,
    PEER_VOTE_SYSTEM,
};
pub use prompt::{build_llm_prompt, LLM_JUDGE_SYSTEM};
pub use redundancy::{
    focus_tags_relevant, has_open_question, judgment_echoes_recent, member_recently_redundant,
    text_similarity, trigger_echoes_recent,
};
pub use resolve::{resolve_llm_target, LlmJudgeTarget};
pub use types::{
    GroupJudgeSettings, HeuristicJudgeSettings, JudgeMode, JudgeSource, Judgment,
    LlmJudgeSettings, TriggerSenderKind,
};
