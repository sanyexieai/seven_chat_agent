use crate::types::GroupJudgeSettings;

#[derive(Debug, Clone, serde::Deserialize)]
pub struct DelegateResumeRaw {
    pub should_resume: bool,
    #[serde(default)]
    pub reason: Option<String>,
    #[serde(default)]
    pub confidence: Option<f32>,
}

pub const DELEGATE_RESUME_SYSTEM: &str =
    "你是任务流调度助手。根据用户代理人（替身）发言，判断是否应恢复负责人/专家执行。只输出 JSON。";

pub fn parse_delegate_resume_response(text: &str) -> Option<DelegateResumeRaw> {
    let start = text.find('{')?;
    let end = text.rfind('}')?;
    if end < start {
        return None;
    }
    serde_json::from_str(&text[start..=end]).ok()
}

pub fn build_delegate_resume_prompt(
    group_judge: &GroupJudgeSettings,
    user_task: &str,
    task_outcome: &str,
    delegate_reply: &str,
    extra_group_prompt: Option<&str>,
) -> String {
    let extra = extra_group_prompt
        .filter(|s| !s.trim().is_empty())
        .map(|s| format!("\n群补充说明：{s}\n"))
        .unwrap_or_default();
    format!(
        "群配置 judge 模式：{:?}。{extra}\n用户本轮任务：\n{task}\n\n\
        任务流当前状态：{outcome}\n\n用户代理人（代主人）发言：\n{reply}\n\n\
        判定是否应 **恢复执行**（should_resume=true）：\n\
        - 代理人明确授权继续推进、分工执行、无需主人每轮确认 → true\n\
        - 代理人要求暂停、等待主人决定、仅同步知悉无执行授权 → false\n\
        - 任务已可验收交付、仅作收尾致谢 → false\n\n\
        只输出 JSON：{{\"should_resume\": true/false, \"reason\": \"一句话\", \"confidence\": 0.0-1.0}}",
        group_judge.mode,
        task = truncate(user_task, 1000),
        outcome = task_outcome,
        reply = truncate(delegate_reply, 2000),
    )
}

/// LLM 不可用：任务未交付且代理人已发言 → 倾向恢复（不依赖关键词表）。
pub fn heuristic_delegate_resume(task_not_delivered: bool, delegate_reply: &str) -> DelegateResumeRaw {
    let reply = delegate_reply.trim();
    if !task_not_delivered || reply.is_empty() {
        return DelegateResumeRaw {
            should_resume: false,
            reason: Some("任务已交付或代理人无实质发言（启发式）".into()),
            confidence: Some(0.5),
        };
    }
    DelegateResumeRaw {
        should_resume: true,
        reason: Some("任务未交付且代理人已发言，默认恢复执行（启发式）".into()),
        confidence: Some(0.45),
    }
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        return s.to_string();
    }
    let mut out: String = s.chars().take(max).collect();
    out.push('…');
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn heuristic_resumes_when_not_delivered() {
        let r = heuristic_delegate_resume(true, "方案已定，请负责人协调成员推进。");
        assert!(r.should_resume);
    }

    #[test]
    fn heuristic_skips_when_delivered() {
        let r = heuristic_delegate_resume(false, "继续推进");
        assert!(!r.should_resume);
    }
}
