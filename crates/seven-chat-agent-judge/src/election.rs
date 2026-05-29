use serde::Deserialize;

use crate::types::GroupJudgeSettings;

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        return s.to_string();
    }
    let mut t: String = s.chars().take(max).collect();
    t.push('…');
    t
}

/// 负责人选举 LLM 系统提示。
pub const ELECTION_SYSTEM: &str =
    "你是群任务协调者。根据成员的竞选发言，选出最适合担任本轮任务负责人的一人。只输出 JSON。";

/// 构建选举 prompt。
pub fn build_election_prompt(
    group_judge: &GroupJudgeSettings,
    user_task: &str,
    pitches: &[(String, String, String)], // (friend_id, friend_name, pitch_content)
    peer_vote_tally: Option<&str>,
    extra_group_prompt: Option<&str>,
) -> String {
    let pitches_text = pitches
        .iter()
        .map(|(id, name, content)| {
            format!(
                "- id=\"{id}\"  name=\"{name}\"\n  竞选发言：{content}",
                content = truncate(content, 800)
            )
        })
        .collect::<Vec<_>>()
        .join("\n\n");
    let extra = extra_group_prompt
        .filter(|s| !s.trim().is_empty())
        .map(|s| format!("\n群补充说明：{s}\n"))
        .unwrap_or_default();
    let votes = peer_vote_tally
        .filter(|s| !s.trim().is_empty())
        .map(|s| format!("\n成员互投统计（背书票，供参考）：\n{s}\n"))
        .unwrap_or_default();
    format!(
        "群配置 judge 模式：{:?}。{extra}{votes}\n用户本轮任务：\n{task}\n\n以下成员竞选负责人（已陈述优势与能胜任的理由）：\n{pitches_text}\n\n请选出唯一负责人。评估：专业匹配度、能否执行（工具/CLI）、计划是否清晰、是否避免重复劳动；若互投统计明显倾向某人，应与之对齐除非有充分反证。\n只输出 JSON：{{\"leader_id\": \"成员id\", \"leader_name\": \"成员名\", \"reason\": \"为何选他/她（一句话）\", \"confidence\": 0.0-1.0}}",
        group_judge.mode,
        task = truncate(user_task, 1200),
    )
}

/// 成员互投（背书）解析。
#[derive(Debug, Deserialize)]
pub struct PeerVoteRaw {
    pub endorse_leader_id: String,
    #[serde(default)]
    pub reason: Option<String>,
}

pub const PEER_VOTE_SYSTEM: &str =
    "你是群成员，阅读竞选发言后为负责人投票（背书）。只输出 JSON。";

pub fn build_peer_vote_prompt(
    voter_name: &str,
    voter_id: &str,
    user_task: &str,
    pitches: &[(String, String, String)],
) -> String {
    let pitches_text = pitches
        .iter()
        .map(|(id, name, content)| {
            format!(
                "- id=\"{id}\" name=\"{name}\"\n  {}",
                content = truncate(content, 500)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    format!(
        "你是「{voter_name}」（id={voter_id}）。用户任务：{task}\n\n竞选发言：\n{pitches_text}\n\n请投票背书你认为最合适的负责人（不能投自己 id={voter_id}）。\n只输出 JSON：{{\"endorse_leader_id\": \"成员id\", \"reason\": \"一句话理由\"}}",
        task = truncate(user_task, 600),
    )
}

pub fn parse_peer_vote_response(text: &str) -> Option<PeerVoteRaw> {
    let body = extract_json(text)?;
    serde_json::from_str(&body).ok()
}

/// 统计互投：返回 (leader_id, 票数) 列表，按票数降序。
pub fn tally_peer_votes(votes: &[(String, String)]) -> Vec<(String, u32)> {
    use std::collections::HashMap;
    let mut counts: HashMap<String, u32> = HashMap::new();
    for (_, endorse_id) in votes {
        *counts.entry(endorse_id.clone()).or_insert(0) += 1;
    }
    let mut out: Vec<_> = counts.into_iter().collect();
    out.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    out
}

pub fn format_peer_vote_tally(
    votes: &[(String, String)],
    id_to_name: &[(String, String)],
) -> String {
    let tallied = tally_peer_votes(votes);
    if tallied.is_empty() {
        return "（无有效投票）".into();
    }
    tallied
        .iter()
        .map(|(id, n)| {
            let name = id_to_name
                .iter()
                .find(|(i, _)| i == id)
                .map(|(_, nm)| nm.as_str())
                .unwrap_or(id.as_str());
            format!("- {name} (id={id}): {n} 票")
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[derive(Debug, Deserialize)]
pub struct ElectionRaw {
    pub leader_id: String,
    #[serde(default)]
    pub leader_name: Option<String>,
    #[serde(default)]
    pub reason: Option<String>,
    #[serde(default)]
    pub confidence: Option<f32>,
}

pub fn parse_election_response(text: &str) -> Option<ElectionRaw> {
    let body = extract_json(text)?;
    serde_json::from_str(&body).ok()
}

fn extract_json(text: &str) -> Option<String> {
    let start = text.find('{')?;
    let end = text.rfind('}')?;
    if end >= start {
        Some(text[start..=end].to_string())
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_election_json() {
        let raw = parse_election_response(r#"{"leader_id":"a","leader_name":"码农","reason":"能写代码"}"#);
        assert!(raw.is_some());
        assert_eq!(raw.unwrap().leader_id, "a");
    }
}
