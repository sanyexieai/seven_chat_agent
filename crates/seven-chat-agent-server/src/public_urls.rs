//! 对外展示的 URL（配对 CLI relay 等），与 `main.rs` 中 HTTPS 跳转逻辑一致。

use std::net::SocketAddr;

/// 解析 CLI relay WebSocket 地址：全局设置覆盖 → 环境变量推导 → 按 `ws_scheme` 应用协议。
///
/// `ws_scheme`：`auto` | `ws` | `wss`（来自全局设置 `cli_relay_ws_scheme`）。
pub fn resolve_cli_relay_ws_url(settings_override: Option<&str>, ws_scheme: &str) -> String {
    let raw = settings_override
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(|s| normalize_relay_ws_input(s, ws_scheme))
        .unwrap_or_else(cli_relay_ws_url);
    apply_ws_scheme(&raw, ws_scheme)
}

/// Web 端「生成配对码」返回的 CLI relay WebSocket 地址（无全局覆盖时）。
///
/// 优先级：`RELAY_WS_URL` → `PUBLIC_ORIGIN` 推导 → 已启用 HTTPS → `ws://BIND`。
pub fn cli_relay_ws_url() -> String {
    if let Some(url) = seven_chat_agent_core::env::var(
        "SEVEN_CHAT_AGENT_RELAY_WS_URL",
        "HONEYCOMB_RELAY_WS_URL",
    ) {
        return url;
    }

    if let Some(origin) = seven_chat_agent_core::env::var(
        "SEVEN_CHAT_AGENT_PUBLIC_ORIGIN",
        "HONEYCOMB_PUBLIC_ORIGIN",
    ) {
        return origin_to_relay_ws_url(&origin);
    }

    if https_enabled() {
        let host = public_host().unwrap_or_else(|| "127.0.0.1".to_string());
        let port = public_https_port(https_listen_port().unwrap_or(443));
        if port == 443 {
            return format!("wss://{host}/cli-relay");
        }
        return format!("wss://{host}:{port}/cli-relay");
    }

    let bind = seven_chat_agent_core::env::var_or(
        "SEVEN_CHAT_AGENT_BIND",
        "HONEYCOMB_BIND",
        "127.0.0.1:18737",
    );
    let addr: SocketAddr = bind
        .parse()
        .unwrap_or_else(|_| "127.0.0.1:18737".parse().expect("fallback addr"));
    let host = public_host().unwrap_or_else(|| normalize_listen_host(&addr.ip().to_string()));
    if addr.port() == 80 {
        format!("ws://{host}/cli-relay")
    } else {
        format!("ws://{host}:{}/cli-relay", addr.port())
    }
}

fn https_enabled() -> bool {
    seven_chat_agent_core::env::var("SEVEN_CHAT_AGENT_TLS_CERT", "HONEYCOMB_TLS_CERT")
        .is_some()
        && seven_chat_agent_core::env::var("SEVEN_CHAT_AGENT_HTTPS_BIND", "HONEYCOMB_HTTPS_BIND")
            .is_some()
}

fn https_listen_port() -> Option<u16> {
    let raw =
        seven_chat_agent_core::env::var("SEVEN_CHAT_AGENT_HTTPS_BIND", "HONEYCOMB_HTTPS_BIND")?;
    raw.parse::<SocketAddr>().ok().map(|a| a.port())
}

fn public_https_port(listen_port: u16) -> u16 {
    seven_chat_agent_core::env::var(
        "SEVEN_CHAT_AGENT_PUBLIC_HTTPS_PORT",
        "HONEYCOMB_PUBLIC_HTTPS_PORT",
    )
    .and_then(|s| s.parse().ok())
    .unwrap_or(listen_port)
}

fn public_host() -> Option<String> {
    seven_chat_agent_core::env::var("SEVEN_CHAT_AGENT_PUBLIC_HOST", "HONEYCOMB_PUBLIC_HOST")
}

/// 将 `https://host:port` / `http://host:port` 转为 relay WebSocket 地址。
fn origin_to_relay_ws_url(origin: &str) -> String {
    let t = origin.trim().trim_end_matches('/');
    let ws_base = if let Some(rest) = t.strip_prefix("https://") {
        format!("wss://{rest}")
    } else if let Some(rest) = t.strip_prefix("http://") {
        format!("ws://{rest}")
    } else {
        format!("wss://{t}")
    };
    format!("{ws_base}/cli-relay")
}

/// 在已启用 TLS 或对外 Origin 为 HTTPS 时，将 `ws://` 升级为 `wss://`（`auto` 模式）。
pub fn prefer_wss_url(url: &str) -> String {
    apply_ws_scheme(url, "auto")
}

/// 按全局协议设置调整 WebSocket URL。
pub fn apply_ws_scheme(url: &str, ws_scheme: &str) -> String {
    let u = url.trim();
    match ws_scheme.trim().to_ascii_lowercase().as_str() {
        "wss" => force_ws_scheme(u, "wss"),
        "ws" => force_ws_scheme(u, "ws"),
        _ => {
            if u.starts_with("wss://") {
                return u.to_string();
            }
            if u.starts_with("ws://") && wss_preferred() {
                return u.replacen("ws://", "wss://", 1);
            }
            u.to_string()
        }
    }
}

fn force_ws_scheme(url: &str, scheme: &str) -> String {
    let u = url.trim();
    let rest = u
        .strip_prefix("wss://")
        .or_else(|| u.strip_prefix("ws://"))
        .unwrap_or(u);
    format!("{scheme}://{rest}")
}

fn normalize_relay_ws_input(s: &str, ws_scheme: &str) -> String {
    let t = s.trim().trim_end_matches('/');
    if t.starts_with("wss://") || t.starts_with("ws://") {
        if t.ends_with("/cli-relay") {
            t.to_string()
        } else {
            format!("{t}/cli-relay")
        }
    } else {
        let scheme = match ws_scheme.trim().to_ascii_lowercase().as_str() {
            "wss" => "wss",
            "ws" => "ws",
            _ => {
                if wss_preferred() {
                    "wss"
                } else {
                    "ws"
                }
            }
        };
        format!("{scheme}://{}/cli-relay", t.trim_start_matches('/'))
    }
}

fn wss_preferred() -> bool {
    if https_enabled() {
        return true;
    }
    seven_chat_agent_core::env::var(
        "SEVEN_CHAT_AGENT_PUBLIC_ORIGIN",
        "HONEYCOMB_PUBLIC_ORIGIN",
    )
    .is_some_and(|o| o.trim().starts_with("https://"))
}

fn normalize_listen_host(ip: &str) -> String {
    if ip == "0.0.0.0" || ip == "::" || ip == "::0" || ip.is_empty() {
        "127.0.0.1".to_string()
    } else {
        ip.to_string()
    }
}
