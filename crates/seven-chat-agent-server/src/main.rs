use std::net::SocketAddr;
use std::path::PathBuf;

use anyhow::Context;
use axum::extract::{Host, OriginalUri, State};
use axum::response::{IntoResponse, Redirect};
use axum::routing::any;
use axum::Router;
use axum_server::tls_rustls::RustlsConfig;
use seven_chat_agent_core::config::CoreConfig;
use seven_chat_agent_core::{AssistantQueueTask, SevenChatAgent};
use seven_chat_agent_server::{build_app_with_static, static_assets};
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // 从当前工作目录向上查找 .env（不覆盖已导出的变量）
    let _ = dotenvy::dotenv();

    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info,seven_chat_agent_core=debug,seven_chat_agent_server=debug")))
        .init();

    let cfg = CoreConfig::from_env();
    std::fs::create_dir_all(&cfg.data_dir).ok();

    let agent = SevenChatAgent::boot(&cfg.database_url)
        .await
        .context("boot seven-chat-agent core")?;
    let _ = agent
        .enqueue_assistant_task_after(AssistantQueueTask::IdleTick, 5)
        .await;
    let _ = agent
        .enqueue_assistant_task_after(AssistantQueueTask::SyncSkills, 20)
        .await;
    let _ = agent
        .enqueue_assistant_task_after(AssistantQueueTask::ConsolidateMemory, 30)
        .await;

    match seven_chat_agent_core::friend_cli::ensure_worker_bee_executable() {
        Ok(path) => tracing::info!(%path, "worker-bee CLI available (optional tools)"),
        Err(e) => tracing::debug!(
            "{e} — 工蜂对话仍走 Provider API；仅「cli」工具或外部 CLI 预设需要 worker-bee 二进制"
        ),
    }

    let static_dir = resolve_static_dir();
    if let Some(dir) = &static_dir {
        tracing::info!(path = %dir.display(), "serving static frontend");
    }
    let app = build_app_with_static(agent, static_dir);

    let addr: SocketAddr = seven_chat_agent_core::env::var_or(
        "SEVEN_CHAT_AGENT_BIND",
        "HONEYCOMB_BIND",
        "127.0.0.1:18737",
    )
    .parse()
    .context("SEVEN_CHAT_AGENT_BIND / HONEYCOMB_BIND")?;

    let https_addr = https_bind_addr()?;
    if let Some(https_addr) = https_addr {
        let cert_path = var_or_opt("SEVEN_CHAT_AGENT_TLS_CERT", "HONEYCOMB_TLS_CERT")
            .ok_or_else(|| anyhow::anyhow!("SEVEN_CHAT_AGENT_TLS_CERT / HONEYCOMB_TLS_CERT required when HTTPS is enabled"))?;
        let key_path = var_or_opt("SEVEN_CHAT_AGENT_TLS_KEY", "HONEYCOMB_TLS_KEY")
            .ok_or_else(|| anyhow::anyhow!("SEVEN_CHAT_AGENT_TLS_KEY / HONEYCOMB_TLS_KEY required when HTTPS is enabled"))?;

        let tls = RustlsConfig::from_pem_file(PathBuf::from(cert_path), PathBuf::from(key_path))
            .await
            .context("load TLS cert/key")?;

        tracing::info!(%addr, %https_addr, "seven-chat-agent-server listening (http->https + https)");
        let redirect_app = build_http_redirect_app(https_addr);
        let http = async move {
            let listener = tokio::net::TcpListener::bind(addr).await?;
            axum::serve(listener, redirect_app).await?;
            anyhow::Ok(())
        };
        let https = async move {
            axum_server::bind_rustls(https_addr, tls)
                .serve(app.into_make_service())
                .await?;
            anyhow::Ok(())
        };
        let (_http, _https) = tokio::try_join!(http, https)?;
    } else {
        tracing::info!(%addr, "seven-chat-agent-server listening (http)");
        let listener = tokio::net::TcpListener::bind(addr).await?;
        axum::serve(listener, app).await?;
    }
    Ok(())
}

/// 优先级：`SEVEN_CHAT_AGENT_STATIC_DIR` env 显式指定 > 当前目录下 `web/dist` 自动探测。
fn resolve_static_dir() -> Option<PathBuf> {
    if let Some(p) = static_assets::static_dir_from_env() {
        return Some(p);
    }
    for candidate in ["web/dist", "../web/dist", "../../web/dist"] {
        let p = PathBuf::from(candidate);
        if p.join("index.html").is_file() {
            return Some(p);
        }
    }
    None
}

fn var_or_opt(primary: &str, fallback: &str) -> Option<String> {
    std::env::var(primary)
        .ok()
        .or_else(|| std::env::var(fallback).ok())
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty())
}

fn https_bind_addr() -> anyhow::Result<Option<SocketAddr>> {
    let raw = var_or_opt("SEVEN_CHAT_AGENT_HTTPS_BIND", "HONEYCOMB_HTTPS_BIND");
    let Some(raw) = raw else {
        return Ok(None);
    };
    let addr = raw
        .parse()
        .with_context(|| format!("SEVEN_CHAT_AGENT_HTTPS_BIND / HONEYCOMB_HTTPS_BIND: {raw}"))?;
    Ok(Some(addr))
}

fn build_http_redirect_app(https_addr: SocketAddr) -> Router {
    Router::new()
        .route("/{*path}", any(http_to_https_redirect))
        .with_state(https_addr)
}

async fn http_to_https_redirect(
    State(https_addr): State<SocketAddr>,
    host: Option<Host>,
    OriginalUri(uri): OriginalUri,
) -> impl IntoResponse {
    let host_value = host
        .map(|h| h.0)
        .unwrap_or_else(|| https_addr.ip().to_string());
    let host_without_port = if host_value.starts_with('[') {
        host_value
            .split("]:")
            .next()
            .map(|v| format!("{v}]"))
            .unwrap_or(host_value)
    } else {
        host_value
            .split(':')
            .next()
            .map(str::to_string)
            .unwrap_or(host_value)
    };
    let location = format!("https://{}:{}{}", host_without_port, https_addr.port(), uri);
    Redirect::permanent(&location)
}
