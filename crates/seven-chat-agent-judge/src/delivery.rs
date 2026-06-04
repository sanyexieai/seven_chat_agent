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

/// 任务交付判定 LLM 系统提示。
pub const DELIVERY_CHECK_SYSTEM: &str =
    "你是群任务验收协调者。判断负责人对用户的最新回复是否已形成「明确交付」。只输出 JSON。";

/// 构建交付判定 prompt。
pub fn build_delivery_check_prompt(
    group_judge: &GroupJudgeSettings,
    user_task: &str,
    plan_text: &str,
    leader_name: &str,
    leader_reply: &str,
    extra_group_prompt: Option<&str>,
) -> String {
    let extra = extra_group_prompt
        .filter(|s| !s.trim().is_empty())
        .map(|s| format!("\n群补充说明：{s}\n"))
        .unwrap_or_default();
    let plan = if plan_text.trim().is_empty() {
        "（无单独计划稿）".to_string()
    } else {
        truncate(plan_text, 1500)
    };
    format!(
        "群配置 judge 模式：{:?}。{extra}\n用户本轮任务：\n{task}\n\n执行计划：\n{plan}\n\n负责人「{leader}」最新回复：\n{reply}\n\n\
        判定标准（delivered=true 须同时满足）：\n\
        1. 用户能明确知道「得到了什么」——具体产出/结论/可验收结果（代码变更、文档、决策、可执行步骤清单等），而非仅承诺或过程描述\n\
        2. 若任务要求执行/调研/写代码，回复中应有实质内容或清晰完成说明，不能停在「我去看看」「还需要信息」\n\
        3. 若任务本身只需讨论收敛，须看到各方观点已汇总且给出可执行下一步或最终建议\n\n\
        delivered=false 典型情况：仍在提问、只有中间进度、工具失败未解决、空泛总结、明确说尚未完成\n\n\
        只输出 JSON：{{\"delivered\": true/false, \"reason\": \"一句话\", \"missing\": \"若未交付还缺什么（可空）\", \"confidence\": 0.0-1.0}}",
        group_judge.mode,
        task = truncate(user_task, 1200),
        plan = plan,
        leader = leader_name,
        reply = truncate(leader_reply, 2500),
    )
}

#[derive(Debug, Clone, Deserialize)]
pub struct DeliveryCheckRaw {
    pub delivered: bool,
    #[serde(default)]
    pub reason: Option<String>,
    #[serde(default)]
    pub missing: Option<String>,
    #[serde(default)]
    pub confidence: Option<f32>,
}

pub fn parse_delivery_check_response(text: &str) -> Option<DeliveryCheckRaw> {
    let start = text.find('{')?;
    let end = text.rfind('}')?;
    if end < start {
        return None;
    }
    serde_json::from_str(&text[start..=end]).ok()
}

/// LLM 不可用时的保守启发式：宁可继续引导，勿过早结束。
pub fn heuristic_delivery_check(leader_reply: &str) -> DeliveryCheckRaw {
    let reply = leader_reply.trim();
    let lower = reply.to_lowercase();
    let not_signals = [
        "待确认",
        "还需要",
        "下一步",
        "尚未",
        "无法完成",
        "请提供",
        "不清楚",
        "待补充",
        "进行中",
        "稍后",
        "failed",
        "error",
        "?",
        "？",
    ];
    if not_signals.iter().any(|s| reply.contains(s) || lower.contains(s)) {
        return DeliveryCheckRaw {
            delivered: false,
            reason: Some("回复含未完成信号（启发式）".into()),
            missing: Some("需继续推进或向用户澄清".into()),
            confidence: Some(0.4),
        };
    }
    let delivered_signals = [
        "交付",
        "已完成",
        "完成总结",
        "验收",
        "产出如下",
        "结果如下",
        "变更如下",
        "最终方案",
        "结论：",
    ];
    if reply.chars().count() >= 120
        && delivered_signals.iter().any(|s| reply.contains(s))
    {
        return DeliveryCheckRaw {
            delivered: true,
            reason: Some("回复含完成/交付信号且足够具体（启发式）".into()),
            missing: None,
            confidence: Some(0.55),
        };
    }
    DeliveryCheckRaw {
        delivered: false,
        reason: Some("未检测到明确交付物（启发式保守判定）".into()),
        missing: Some("请负责人继续引导或给出可验收产出".into()),
        confidence: Some(0.35),
    }
}

/// 内置助理：监控负责人引导是否陷入空转。
pub const STAGNATION_CHECK_SYSTEM: &str =
    "你是群内置助理 Hex，负责监控任务引导循环，避免无意义空转。只输出 JSON。";

#[derive(Debug, Clone, Deserialize)]
pub struct StagnationCheckRaw {
    pub should_stop: bool,
    #[serde(default)]
    pub reason: Option<String>,
    #[serde(default)]
    pub suggestion: Option<String>,
    #[serde(default)]
    pub confidence: Option<f32>,
}

pub fn parse_stagnation_check_response(text: &str) -> Option<StagnationCheckRaw> {
    let start = text.find('{')?;
    let end = text.rfind('}')?;
    if end < start {
        return None;
    }
    serde_json::from_str(&text[start..=end]).ok()
}

pub fn build_stagnation_check_prompt(
    group_judge: &GroupJudgeSettings,
    user_task: &str,
    plan_text: &str,
    leader_name: &str,
    leader_replies: &[String],
    last_missing: &str,
    extra_group_prompt: Option<&str>,
    delegate_autonomous_directive: Option<&str>,
) -> String {
    let extra = extra_group_prompt
        .filter(|s| !s.trim().is_empty())
        .map(|s| format!("\n群补充说明：{s}\n"))
        .unwrap_or_default();
    let plan = if plan_text.trim().is_empty() {
        "（无单独计划稿）".to_string()
    } else {
        truncate(plan_text, 1200)
    };
    let rounds = leader_replies
        .iter()
        .enumerate()
        .map(|(i, r)| format!("--- 第 {} 轮 ---\n{}", i + 1, truncate(r, 1200)))
        .collect::<Vec<_>>()
        .join("\n\n");
    let delegate_note = delegate_autonomous_directive
        .filter(|s| !s.trim().is_empty())
        .map(|s| format!(
            "\n用户代理人已授权自主推进（无需主人每轮确认）：\n{}\n\
            在此授权下 should_stop 应为 false，除非出现明确不可恢复错误。\n",
            truncate(s, 800)
        ))
        .unwrap_or_default();
    format!(
        "群配置 judge 模式：{:?}。{extra}\n用户本轮任务：\n{task}\n\n计划：\n{plan}\n\n\
        负责人「{leader}」已进行 {n} 轮回复，最新验收缺口：{missing}\n\n各轮回复：\n{rounds}\n\
        {delegate_note}\n\
        作为内置助理，判断引导循环是否应 **暂停**（should_stop=true）：\n\
        - 连续多轮内容高度重复、无新信息或新进展\n\
        - 负责人反复问同样问题、在原地打转\n\
        - 已明确阻塞且必须等待用户/外部输入，继续自动引导无意义\n\
        - 工具/环境错误无法在本轮内自行解决\n\
        should_stop=false：仍有实质推进空间，负责人应继续引导\n\n\
        只输出 JSON：{{\"should_stop\": true/false, \"reason\": \"一句话\", \"suggestion\": \"给用户的建议（可空）\", \"confidence\": 0.0-1.0}}",
        group_judge.mode,
        task = truncate(user_task, 1000),
        plan = plan,
        leader = leader_name,
        n = leader_replies.len(),
        missing = last_missing,
        rounds = rounds,
    )
}

/// 启发式空转检测：最近两轮回复高度相似则暂停。
pub fn heuristic_stagnation_check(
    leader_replies: &[String],
    min_leader_rounds: u32,
    similarity_threshold: f32,
) -> StagnationCheckRaw {
    let min = min_leader_rounds.max(2) as usize;
    if leader_replies.len() < min {
        return StagnationCheckRaw {
            should_stop: false,
            reason: Some("轮次不足，继续引导".into()),
            suggestion: None,
            confidence: Some(0.3),
        };
    }
    let a = leader_replies[leader_replies.len() - 2].as_str();
    let b = leader_replies[leader_replies.len() - 1].as_str();
    let sim = reply_similarity(a, b);
    if sim >= similarity_threshold.clamp(0.5, 1.0) {
        return StagnationCheckRaw {
            should_stop: true,
            reason: Some(format!("最近两轮回复高度相似（{sim:.0}%），疑似空转（启发式）")),
            suggestion: Some("请用户补充信息或调整任务范围，再 @ 负责人继续".into()),
            confidence: Some(0.65),
        };
    }
    StagnationCheckRaw {
        should_stop: false,
        reason: Some("未检测到明显空转（启发式）".into()),
        suggestion: None,
        confidence: Some(0.4),
    }
}

fn reply_similarity(a: &str, b: &str) -> f32 {
    use std::collections::HashSet;
    let bag_a: HashSet<&str> = a.split_whitespace().collect();
    let bag_b: HashSet<&str> = b.split_whitespace().collect();
    if bag_a.is_empty() || bag_b.is_empty() {
        return 0.0;
    }
    let inter = bag_a.intersection(&bag_b).count();
    let uni = bag_a.union(&bag_b).count();
    inter as f32 / uni as f32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_delivery_json() {
        let raw = parse_delivery_check_response(
            r#"{"delivered":false,"reason":"只有问题","missing":"需要代码 diff"}"#,
        );
        assert!(raw.as_ref().is_some_and(|r| !r.delivered));
    }

    #[test]
    fn heuristic_flags_incomplete() {
        let r = heuristic_delivery_check("还需要你提供仓库地址，我下一步再查。");
        assert!(!r.delivered);
    }

    #[test]
    fn heuristic_stagnation_detects_repeat() {
        let text = "请提供仓库地址和分支名，我才能在本地 clone 并检查代码。".to_string();
        let replies = vec![text.clone(), text.clone(), text];
        assert!(heuristic_stagnation_check(&replies, 3, 0.88).should_stop);
    }

    #[test]
    fn heuristic_stagnation_needs_min_rounds() {
        let text = "请提供仓库地址".to_string();
        let replies = vec![text.clone(), text];
        assert!(!heuristic_stagnation_check(&replies, 3, 0.88).should_stop);
    }
}
