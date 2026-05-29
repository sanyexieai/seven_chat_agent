//! 环境变量：优先 `SEVEN_CHAT_AGENT_*`，兼容旧版 `HONEYCOMB_*`。

/// 读取环境变量，`primary` 优先，其次 `legacy`。
pub fn var(primary: &str, legacy: &str) -> Option<String> {
    std::env::var(primary)
        .ok()
        .filter(|s| !s.trim().is_empty())
        .or_else(|| {
            std::env::var(legacy)
                .ok()
                .filter(|s| !s.trim().is_empty())
        })
}

pub fn var_or(primary: &str, legacy: &str, default: impl Into<String>) -> String {
    var(primary, legacy).unwrap_or_else(|| default.into())
}
