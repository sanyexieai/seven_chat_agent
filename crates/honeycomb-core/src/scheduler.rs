use std::collections::HashMap;
use std::collections::HashSet;
use std::sync::Arc;
use std::time::{Duration, Instant};

use parking_lot::Mutex;
use serde::{Deserialize, Serialize};

use crate::agent::Judgment;
use crate::domain::{BackendKind, GroupSettings, Message};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CandidateInfo {
    pub friend_id: String,
    pub friend_name: String,
    pub backend_kind: BackendKind,
    pub judgment: Judgment,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScheduleDecision {
    pub friend_id: String,
    pub friend_name: String,
    pub confidence: f32,
    pub delay_ms: u64,
    pub reason: Option<String>,
}

#[derive(Debug, Default)]
struct TurnTrack {
    used_total: u32,
    used_per_agent: HashMap<String, u32>,
    recent_replies: Vec<String>,
    last_speak_at: HashMap<String, Instant>,
    chain_actors: HashMap<String, u32>,
}

#[derive(Clone, Default)]
pub struct SpeakerScheduler {
    turns: Arc<Mutex<HashMap<String, TurnTrack>>>,
}

impl SpeakerScheduler {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn reset_turn(&self, turn_id: &str) {
        self.turns.lock().remove(turn_id);
    }

    pub fn rank(
        &self,
        turn_id: &str,
        settings: &GroupSettings,
        triggering: &Message,
        candidates: Vec<CandidateInfo>,
        parent_chain_actors: &HashMap<String, u32>,
        has_typing_human: bool,
    ) -> Vec<ScheduleDecision> {
        let mut turns = self.turns.lock();
        let track = turns.entry(turn_id.to_string()).or_default();
        let now = Instant::now();

        let budget_left = settings
            .max_replies_per_turn
            .saturating_sub(track.used_total);
        if budget_left == 0 {
            return vec![];
        }

        let threshold = settings.effective_judge_threshold();
        let mut filtered = Self::rank_candidates(
            &candidates,
            triggering,
            settings,
            track,
            parent_chain_actors,
            now,
            true,
            threshold,
        );

        let mut used_fallback = false;
        if filtered.is_empty() && settings.fallback_pick_top_enabled() {
            filtered = Self::rank_candidates(
                &candidates,
                triggering,
                settings,
                track,
                parent_chain_actors,
                now,
                false,
                threshold,
            );
            if !filtered.is_empty() {
                filtered.truncate(1);
                used_fallback = true;
            }
        }

        let mut decisions = Vec::new();
        let mut taken = 0u32;
        for (cand, score) in filtered {
            if taken >= budget_left {
                break;
            }
            let base_delay = cand.judgment.suggested_delay_ms;
            let mut delay = base_delay
                .max(((1.0 - score) * 2000.0) as u64)
                .min(settings.cooldown_ms.saturating_mul(2));
            if has_typing_human && settings.human_priority {
                delay = delay.max(settings.human_pause_ms / 6);
            }
            let reason = if used_fallback && taken == 0 {
                Some(format!(
                    "未达 judge 阈值 {:.2}，按最高分兜底接话（score={score:.2}）",
                    threshold
                ))
            } else {
                cand.judgment.reason.clone()
            };
            decisions.push(ScheduleDecision {
                friend_id: cand.friend_id.clone(),
                friend_name: cand.friend_name.clone(),
                confidence: score,
                delay_ms: delay,
                reason,
            });
            track
                .used_per_agent
                .entry(cand.friend_id.clone())
                .and_modify(|n| *n += 1)
                .or_insert(1);
            *track.chain_actors.entry(cand.friend_id.clone()).or_insert(0) += 1;
            track.last_speak_at.insert(cand.friend_id, now);
            track.used_total += 1;
            taken += 1;
            if used_fallback {
                break;
            }
        }

        decisions
    }

    /// `strict`: 须 `should_reply` 且 confidence ≥ 阈值；否则仅按分数排序（用于全员未过线时兜底 1 人）。
    fn rank_candidates(
        candidates: &[CandidateInfo],
        triggering: &Message,
        settings: &GroupSettings,
        track: &TurnTrack,
        parent_chain_actors: &HashMap<String, u32>,
        now: Instant,
        strict: bool,
        threshold: f32,
    ) -> Vec<(CandidateInfo, f32)> {
        let mut scored: Vec<(CandidateInfo, f32)> = candidates
            .iter()
            .filter(|c| c.backend_kind != BackendKind::Human)
            .filter(|c| c.friend_id != triggering.sender_id)
            .filter(|c| !strict || c.judgment.should_reply)
            .filter(|c| !strict || c.judgment.confidence >= threshold)
            .filter(|c| {
                track.used_per_agent.get(&c.friend_id).copied().unwrap_or(0)
                    < settings.per_agent_max_per_turn
            })
            .filter(|c| {
                track
                    .last_speak_at
                    .get(&c.friend_id)
                    .map(|t| now.duration_since(*t) >= Duration::from_millis(settings.cooldown_ms))
                    .unwrap_or(true)
            })
            .filter(|c| {
                parent_chain_actors.get(&c.friend_id).copied().unwrap_or(0) < 2
                    && track
                        .chain_actors
                        .get(&c.friend_id)
                        .copied()
                        .unwrap_or(0)
                        < 2
            })
            .map(|c| (c.clone(), c.judgment.confidence))
            .filter(|(c, _)| {
                if !strict {
                    return true;
                }
                let new_text = c.judgment.reason.as_deref().unwrap_or("");
                if new_text.is_empty() {
                    return true;
                }
                let near_dup = track
                    .recent_replies
                    .iter()
                    .any(|prev| similarity(prev, new_text) > 0.85);
                !near_dup
            })
            .collect();

        scored.sort_by(|a, b| {
            b.1.partial_cmp(&a.1)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| a.0.friend_id.cmp(&b.0.friend_id))
        });
        scored
    }

    pub fn record_reply(&self, turn_id: &str, reply_excerpt: &str) {
        let mut turns = self.turns.lock();
        let track = turns.entry(turn_id.to_string()).or_default();
        track.recent_replies.push(reply_excerpt.to_string());
        if track.recent_replies.len() > 6 {
            track.recent_replies.remove(0);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::BackendKind;

    fn cand(id: &str, should: bool, conf: f32) -> CandidateInfo {
        CandidateInfo {
            friend_id: id.into(),
            friend_name: id.into(),
            backend_kind: BackendKind::Pty,
            judgment: Judgment {
                should_reply: should,
                confidence: conf,
                reason: None,
                suggested_delay_ms: 0,
                source: None,
            },
        }
    }

    #[test]
    fn fallback_picks_highest_score_when_all_below_threshold() {
        let sched = SpeakerScheduler::new();
        let turn = "t1";
        let settings = GroupSettings {
            judge_threshold: 0.55,
            ..Default::default()
        };
        let trigger = Message {
            id: "m0".into(),
            conversation_id: "c".into(),
            turn_id: turn.into(),
            parent_id: None,
            sender_kind: crate::domain::SenderKind::User,
            sender_id: "user".into(),
            sender_name: "你".into(),
            content: "topic".into(),
            content_blocks: None,
            mentions: vec![],
            status: crate::domain::MessageStatus::Done,
            seen_by: vec![],
            model_used: None,
            tokens_in: None,
            tokens_out: None,
            created_at: chrono::Utc::now(),
        };
        let candidates = vec![
            cand("a", true, 0.3),
            cand("b", true, 0.45),
            cand("c", false, 0.1),
        ];
        let picked = sched.rank(turn, &settings, &trigger, candidates, &HashMap::new(), false);
        assert_eq!(picked.len(), 1);
        assert_eq!(picked[0].friend_id, "b");
        assert!(
            picked[0]
                .reason
                .as_deref()
                .unwrap_or("")
                .contains("兜底")
        );
    }
}

fn similarity(a: &str, b: &str) -> f32 {
    let bag_a: HashSet<&str> = a.split_whitespace().collect();
    let bag_b: HashSet<&str> = b.split_whitespace().collect();
    if bag_a.is_empty() || bag_b.is_empty() {
        return 0.0;
    }
    let inter: usize = bag_a.intersection(&bag_b).count();
    let uni: usize = bag_a.union(&bag_b).count();
    inter as f32 / uni as f32
}
