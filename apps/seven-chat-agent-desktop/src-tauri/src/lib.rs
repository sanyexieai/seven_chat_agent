use std::net::SocketAddr;
use std::sync::mpsc;
use std::time::Duration;

use seven_chat_agent_core::SevenChatAgent;
use seven_chat_agent_server::build_app;
use tauri::Manager;
use tokio::net::TcpListener;

const EMBED_ADDR: &str = "127.0.0.1:18739";
const BOOT_WAIT_SECS: u64 = 12;

#[tauri::command]
async fn ping() -> &'static str {
    "pong"
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info,seven_chat_agent_core=info,seven_chat_agent_desktop=info".into()),
        )
        .init();

    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![ping])
        .setup(|app| {
            let resolver = app.path();
            let local_dir = resolver
                .app_local_data_dir()
                .ok()
                .unwrap_or_else(|| std::path::PathBuf::from(".seven-chat-agent"));
            std::fs::create_dir_all(&local_dir).ok();
            let db_path = local_dir.join("seven_chat_agent.db");
            let db_url = format!("sqlite://{}", db_path.display());
            std::env::set_var(
                "SEVEN_CHAT_AGENT_DATA",
                local_dir.display().to_string(),
            );

            // 阻塞等内嵌 server 真正 bind 到端口再放 webview 加载，
            // 避免初次加载因为 server 还没起而 404。
            let (tx, rx) = mpsc::sync_channel::<anyhow::Result<()>>(1);
            tauri::async_runtime::spawn(async move {
                let started = boot_and_serve(db_url, tx).await;
                if let Err(e) = started {
                    tracing::error!(err=%e, "embedded server stopped");
                }
            });
            match rx.recv_timeout(Duration::from_secs(BOOT_WAIT_SECS)) {
                Ok(Ok(())) => tracing::info!(addr = %EMBED_ADDR, "embedded server ready"),
                Ok(Err(e)) => tracing::error!(err = %e, "embedded server boot failed"),
                Err(_) => {
                    tracing::warn!("embedded server still booting after {BOOT_WAIT_SECS}s");
                }
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

async fn boot_and_serve(
    db_url: String,
    ready_tx: mpsc::SyncSender<anyhow::Result<()>>,
) -> anyhow::Result<()> {
    let agent = match SevenChatAgent::boot(&db_url).await {
        Ok(h) => h,
        Err(e) => {
            let _ = ready_tx.send(Err(anyhow::anyhow!(e.to_string())));
            return Err(anyhow::anyhow!(e.to_string()));
        }
    };
    let app = build_app(agent);
    let addr: SocketAddr = EMBED_ADDR.parse()?;
    let listener = match bind_with_retry(addr).await {
        Ok(l) => l,
        Err(e) => {
            let _ = ready_tx.send(Err(anyhow::anyhow!(e.to_string())));
            return Err(e);
        }
    };
    let _ = ready_tx.send(Ok(()));
    axum::serve(listener, app).await?;
    Ok(())
}

async fn bind_with_retry(addr: SocketAddr) -> anyhow::Result<TcpListener> {
    let mut delay = Duration::from_millis(200);
    for attempt in 0..6 {
        match TcpListener::bind(addr).await {
            Ok(l) => return Ok(l),
            Err(e) if attempt < 5 => {
                tracing::warn!(err=%e, attempt, "bind failed, retrying");
                tokio::time::sleep(delay).await;
                delay = delay.saturating_mul(2);
            }
            Err(e) => return Err(e.into()),
        }
    }
    unreachable!()
}
