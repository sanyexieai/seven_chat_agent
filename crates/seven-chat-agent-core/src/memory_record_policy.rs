//! 记忆写入策略：避免把每条聊天原样灌进长期记忆。
//!
//! 分层原则：
//! - **观察备忘**：其他私聊/群聊里的用户发言，只记「有信息量」且非重复的快照。
//! - **协助回合**：与内置助理对话时，默认不写流水账（由提取/反思写知识）；可选开启完整回合备忘。
//! - **知识库**：仅 LLM 抽取/反思得出的可复用事实，空则不落库。

use crate::domain::AssistantGlobalSettings;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RecordDecision {
    Record,
    Skip(&'static str),
}

impl RecordDecision {
    pub fn should_record(&self) -> bool {
        matches!(self, RecordDecision::Record)
    }
}

/// 是否应对「其他会话」里的用户消息写观察备忘。
pub fn evaluate_observe_message(body: &str, settings: &AssistantGlobalSettings) -> RecordDecision {
    let text = body.trim();
    if text.is_empty() {
        return RecordDecision::Skip("empty");
    }
    let min = settings.record_min_chars.max(1) as usize;
    if text.chars().count() < min {
        return RecordDecision::Skip("too_short");
    }
    if settings.record_skip_low_signal && is_low_signal(text) {
        return RecordDecision::Skip("low_signal");
    }
    RecordDecision::Record
}

/// 是否写「协助记录」备忘（与知识提取互补，默认关闭以免重复）。
pub fn evaluate_assist_memo(
    prompt: &str,
    response: &str,
    settings: &AssistantGlobalSettings,
) -> RecordDecision {
    if !settings.record_assist_memo {
        return RecordDecision::Skip("assist_memo_disabled");
    }
    let p = prompt.trim();
    let r = response.trim();
    if p.is_empty() && r.is_empty() {
        return RecordDecision::Skip("empty_turn");
    }
    let min = settings.record_min_chars.max(1) as usize;
    // 开启自动提取时，协助流水账门槛更高，避免与 knowledge 重复
    let need_chars = if settings.auto_extract_memories {
        (min * 3).max(48)
    } else {
        (min * 2).max(32)
    };
    let total = p.chars().count() + r.chars().count();
    if total < need_chars {
        return RecordDecision::Skip("assist_not_substantive");
    }
    if settings.record_skip_low_signal && is_low_signal(p) && r.chars().count() < min * 2 {
        return RecordDecision::Skip("assist_low_signal");
    }
    RecordDecision::Record
}

/// 用于同一会话 scope 下去重（规范化后的正文指纹）。
pub fn content_fingerprint(body: &str) -> String {
    body.chars()
        .filter(|c| !c.is_whitespace())
        .take(96)
        .flat_map(|c| c.to_lowercase())
        .collect()
}

/// 两条观察内容是否视为重复。
pub fn observe_contents_similar(a: &str, b: &str) -> bool {
    let fa = content_fingerprint(a);
    let fb = content_fingerprint(b);
    if fa.is_empty() || fb.is_empty() {
        return false;
    }
    if fa == fb {
        return true;
    }
    let min_len = fa.len().min(fb.len());
    if min_len < 8 {
        return false;
    }
    fa.starts_with(&fb[..min_len.min(fb.len())])
        || fb.starts_with(&fa[..min_len.min(fa.len())])
}

fn is_low_signal(text: &str) -> bool {
    let t = text.trim();
    if t.is_empty() {
        return true;
    }
    let alnum: usize = t.chars().filter(|c| c.is_alphanumeric()).count();
    if alnum == 0 {
        return true;
    }
    let lower = t.to_lowercase();
    const PHRASES: &[&str] = &[
        "你好",
        "您好",
        "hi",
        "hello",
        "hey",
        "ok",
        "okay",
        "好的",
        "好",
        "嗯",
        "嗯嗯",
        "哦",
        "啊",
        "谢谢",
        "多谢",
        "thanks",
        "thx",
        "收到",
        "明白",
        "知道了",
        "在吗",
        "在不在",
        "？",
        "?",
        "。。",
        "...",
        "👍",
        "🙏",
        "哈哈",
        "hhh",
    ];
    if t.chars().count() <= 12 {
        for p in PHRASES {
            if lower == *p || lower == format!("{p}!") || lower == format!("{p}。") {
                return true;
            }
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    fn settings() -> AssistantGlobalSettings {
        AssistantGlobalSettings::default()
    }

    #[test]
    fn skip_greeting_observe() {
        let d = evaluate_observe_message("你好", &settings());
        assert!(!d.should_record());
    }

    #[test]
    fn record_substantive_observe() {
        let s = settings();
        let d = evaluate_observe_message(
            "请帮我把下周发布会的需求文档整理成三条要点",
            &s,
        );
        assert!(d.should_record());
    }

    #[test]
    fn assist_off_by_default() {
        let s = settings();
        assert!(!evaluate_assist_memo("帮我写个函数", "好的，这是代码……（略）", &s).should_record());
    }

    #[test]
    fn fingerprint_similar() {
        assert!(observe_contents_similar("你好 世界", "你好世界"));
    }
}
