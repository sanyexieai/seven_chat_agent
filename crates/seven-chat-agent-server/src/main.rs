use std::net::SocketAddr;
use std::path::PathBuf;

use anyhow::Context;
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

    let addr: SocketAddr = std::env::var("SEVEN_CHAT_AGENT_BIND")
        .unwrap_or_else(|_| "127.0.0.1:18737".into())
        .parse()
        .context("SEVEN_CHAT_AGENT_BIND")?;

    tracing::info!(%addr, "seven-chat-agent-server listening");
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
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
