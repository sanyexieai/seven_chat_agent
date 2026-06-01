//! 记忆分级模型（参考 Claude Projects / mem0 分层上下文、OpenViking 归档可查思路）。
//!
//! - **tier**: `raw` 原始快照（可查、可归档，默认不进提示词）| `curated` 助理整理后可召回
//! - **scope**: `global` | `user` | `friend` | `conversation` | `workspace` | `ephemeral`
//! - **importance**: 0 临时 … 3 关键
//! - **status**: `active` | `archived`

use crate::domain::{ConvKind, Conversation};

pub const TIER_RAW: &str = "raw";
pub const TIER_CURATED: &str = "curated";

pub const SCOPE_GLOBAL: &str = "global";
pub const SCOPE_USER: &str = "user";
pub const SCOPE_FRIEND: &str = "friend";
pub const SCOPE_CONVERSATION: &str = "conversation";
pub const SCOPE_WORKSPACE: &str = "workspace";
pub const SCOPE_EPHEMERAL: &str = "ephemeral";

pub const STATUS_ACTIVE: &str = "active";
pub const STATUS_ARCHIVED: &str = "archived";

#[derive(Debug, Clone)]
pub struct MemoryScopeKey {
    pub scope: String,
    pub scope_ref: Option<String>,
}

#[derive(Debug, Clone, Default)]
pub struct RecallContext {
    pub conversation_id: Option<String>,
    pub friend_id: Option<String>,
    pub workspace_id: Option<String>,
}

pub fn recall_context_from_chat(ctx: &crate::agent::ChatContext) -> RecallContext {
    RecallContext {
        conversation_id: Some(ctx.conversation_id.clone()),
        friend_id: ctx.peers.first().map(|p| p.id.clone()),
        workspace_id: ctx.self_friend.active_workspace_id.clone(),
    }
}

impl RecallContext {
    pub fn from_conversation(conv: &Conversation) -> Self {
        match conv.kind {
            ConvKind::Dm => Self {
                conversation_id: Some(conv.id.clone()),
                friend_id: Some(conv.target_id.clone()),
                workspace_id: None,
            },
            ConvKind::Group => Self {
                conversation_id: Some(conv.id.clone()),
                friend_id: None,
                workspace_id: None,
            },
        }
    }
}

/// 观察类原始记忆的作用域。
pub fn scope_for_observe(conv: &Conversation) -> MemoryScopeKey {
    match conv.kind {
        ConvKind::Dm => MemoryScopeKey {
            scope: SCOPE_FRIEND.to_string(),
            scope_ref: Some(conv.target_id.clone()),
        },
        ConvKind::Group => MemoryScopeKey {
            scope: SCOPE_CONVERSATION.to_string(),
            scope_ref: Some(conv.id.clone()),
        },
    }
}

pub fn importance_from_weight(weight: f64) -> i32 {
    if weight >= 0.85 {
        3
    } else if weight >= 0.65 {
        2
    } else if weight >= 0.35 {
        1
    } else {
        0
    }
}

pub fn make_summary(content: &str, max_chars: usize) -> String {
    crate::assistant_accumulation::truncate_chars(content, max_chars)
}

pub fn scope_label(scope: &str) -> &'static str {
    match scope {
        SCOPE_GLOBAL => "全局",
        SCOPE_USER => "用户",
        SCOPE_FRIEND => "好友",
        SCOPE_CONVERSATION => "会话",
        SCOPE_WORKSPACE => "工作区",
        SCOPE_EPHEMERAL => "临时",
        _ => "未知",
    }
}

pub fn tier_label(tier: &str) -> &'static str {
    match tier {
        TIER_RAW => "原始",
        TIER_CURATED => "整理",
        _ => "未知",
    }
}

pub fn importance_label(level: i32) -> &'static str {
    match level {
        3 => "关键",
        2 => "重要",
        1 => "一般",
        _ => "临时",
    }
}

pub fn status_label(status: &str) -> &'static str {
    match status {
        STATUS_ARCHIVED => "已归档",
        _ => "活跃",
    }
}

/// 注入系统提示时使用的单行文本（优先 summary）。
pub fn prompt_line(
    scope: &str,
    kind: &str,
    importance: i32,
    summary: Option<&str>,
    content: &str,
) -> String {
    let body = summary
        .filter(|s| !s.trim().is_empty())
        .unwrap_or(content);
    format!(
        "[{}·{}·{}] {}",
        scope_label(scope),
        kind,
        importance_label(importance),
        body.lines().next().unwrap_or(body)
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn importance_buckets() {
        assert_eq!(importance_from_weight(0.9), 3);
        assert_eq!(importance_from_weight(0.1), 0);
    }
}
