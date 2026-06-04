use crate::context::HistoryLine;

/// 词袋 Jaccard 相似度（0~1）。
pub fn text_similarity(a: &str, b: &str) -> f32 {
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

pub fn trigger_echoes_recent(trigger_content: &str, recent: &[String], threshold: f32) -> bool {
    recent
        .iter()
        .any(|r| text_similarity(r, trigger_content) >= threshold)
}

pub fn member_recently_redundant(
    member_name: &str,
    history: &[HistoryLine],
    topic: &str,
    threshold: f32,
) -> bool {
    history
        .iter()
        .rev()
        .take(12)
        .filter(|h| h.sender_name == member_name)
        .any(|h| text_similarity(&h.content, topic) >= threshold)
}

pub fn judgment_echoes_recent(reason: &str, recent: &[String], threshold: f32) -> bool {
    if reason.trim().is_empty() {
        return false;
    }
    recent
        .iter()
        .any(|r| text_similarity(r, reason) >= threshold)
}

/// 触发消息是否含未决疑问（值得接话的信号之一）。
pub fn has_open_question(text: &str) -> bool {
    let t = text.trim();
    t.contains('?')
        || t.contains('？')
        || t.contains("吗")
        || t.contains("么")
        || t.contains("如何")
        || t.contains("怎么")
        || t.contains("为什么")
        || t.contains("是否")
        || t.contains("能否")
        || t.contains("可不可以")
}

pub fn focus_tags_relevant(focus_tags: &[String], text: &str) -> bool {
    focus_tags
        .iter()
        .any(|tag| !tag.trim().is_empty() && text.contains(tag.trim()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_echo() {
        let recent = vec!["请提供仓库地址和分支".into()];
        assert!(trigger_echoes_recent(
            "仍需要你提供仓库地址和分支名",
            &recent,
            0.5
        ));
    }
}
