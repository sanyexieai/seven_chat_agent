use serde::{Deserialize, Serialize};

use crate::types::{GroupJudgeSettings, HeuristicJudgeSettings, JudgeMode, LlmJudgeSettings};

/// 成员级 Judge 覆盖：未启用时完全沿用群 `GroupJudgeSettings`。
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct MemberJudgeOverride {
    /// `true`（默认）= 跟群；`false` = 使用本结构中的非空字段覆盖群配置。
    #[serde(default = "default_true")]
    pub use_group_default: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mode: Option<JudgeMode>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub threshold: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub heuristic: Option<HeuristicJudgeSettings>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub llm: Option<LlmJudgeSettings>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fallback_pick_top: Option<bool>,
}

fn default_true() -> bool {
    true
}

impl MemberJudgeOverride {
    pub fn is_custom(&self) -> bool {
        !self.use_group_default
    }
}

/// 合并群默认与该成员在本群的覆盖，得到生效的 Judge 配置。
///
/// 优先级：本群成员覆盖 > 群 `judge` 默认 >（LLM Provider 见 `resolve_llm_target` 环境变量）。
pub fn resolve_effective_judge(
    group: &GroupJudgeSettings,
    member_in_group: Option<&MemberJudgeOverride>,
    _legacy_unused: Option<&str>,
) -> GroupJudgeSettings {
    let mut eff = group.clone();
    if let Some(m) = member_in_group {
        if m.is_custom() {
            if let Some(mode) = m.mode {
                eff.mode = mode;
            }
            if let Some(t) = m.threshold {
                eff.threshold = t;
            }
            if let Some(ref h) = m.heuristic {
                eff.heuristic = h.clone();
            }
            if let Some(ref llm) = m.llm {
                eff.llm = llm.clone();
            }
            if let Some(fb) = m.fallback_pick_top {
                eff.fallback_pick_top = fb;
            }
        }
    }
    eff
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::GroupJudgeSettings;

    #[test]
    fn member_threshold_overrides_group() {
        let group = GroupJudgeSettings::default();
        let member = MemberJudgeOverride {
            use_group_default: false,
            threshold: Some(0.8),
            ..Default::default()
        };
        let eff = resolve_effective_judge(&group, Some(&member), None);
        assert!((eff.threshold - 0.8).abs() < f32::EPSILON);
        assert_eq!(eff.mode, group.mode);
    }
}
