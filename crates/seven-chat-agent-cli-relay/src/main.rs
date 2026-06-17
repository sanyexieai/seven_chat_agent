//! 在远程电脑上运行的 CLI 转发程序：连接服务端 WebSocket，接收 RunJob 并在本机调用 CLI。

mod auth;
mod executor;
mod output;
mod workspace;

use anyhow::{Context, Result};
use clap::Parser;
use futures::{SinkExt, StreamExt};
use seven_chat_agent_cli_relay_protocol::RelayMessage;
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::info;
use url::Url;

#[derive(Debug, Parser)]
#[command(name = "seven-chat-agent-cli-relay", about = "SevenChatAgent CLI 转发程序（远程本机执行）")]
struct Args {
    /// 服务端 WebSocket 地址，例如 ws://127.0.0.1:8080/cli-relay
    #[arg(long, env = "SEVEN_CHAT_AGENT_RELAY_URL", default_value = "ws://127.0.0.1:18737/cli-relay")]
    url: String,

    /// 在 Web 端生成的配对令牌
    #[arg(long, env = "SEVEN_CHAT_AGENT_RELAY_PAIRING_TOKEN")]
    pairing_token: String,

    /// 本机节点显示名称
    #[arg(long, env = "SEVEN_CHAT_AGENT_RELAY_NAME", default_value = "local-relay")]
    name: String,

    /// 本机 CLI 工作区根目录（留空则用 ~/.local/share/seven-chat-agent/cli-workspaces）
    #[arg(long, env = "SEVEN_CHAT_AGENT_RELAY_WORKSPACE_ROOT")]
    workspace_root: Option<String>,
}

#[tokio::main]
async fn main() -> Result<()> {
    ensure_rustls_crypto_provider()?;

    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let args = Args::parse();
    let url = Url::parse(&args.url).context("invalid relay url")?;
    let workspace_root = args
        .workspace_root
        .filter(|s| !s.trim().is_empty())
        .unwrap_or_else(|| workspace::workspace_root_string());
    info!(%url, name = %args.name, %workspace_root, "connecting to honeycomb cli relay");

    let cli_auth = auth::probe_local_cli_auth().await;
    for p in &cli_auth {
        info!(
            preset = %p.preset,
            authenticated = p.authenticated,
            "relay cli auth probe"
        );
    }

    let (ws, response) = connect_relay(&url).await?;
    info!(status = %response.status(), "websocket connected");
    let (mut write, mut read) = ws.split();

    let register = RelayMessage::Register {
        pairing_token: args.pairing_token.clone(),
        name: args.name.clone(),
        host_label: std::env::var("COMPUTERNAME")
            .ok()
            .or_else(|| std::env::var("HOSTNAME").ok()),
        workspace_root: Some(workspace_root.clone()),
        cli_auth: cli_auth.clone(),
    };
    write
        .send(Message::Text(register.to_json()?))
        .await
        .context("send register")?;

    let (outbound_tx, outbound_rx) = mpsc::channel::<WsOutbound>(256);
    let mut auth_tick = tokio::time::interval(std::time::Duration::from_secs(60));

    // 独立 writer：JobOutput 积压时不阻塞读循环，避免无法接收新 RunJob
    let writer = tokio::spawn(async move {
        let mut rx = outbound_rx;
        while let Some(msg) = rx.recv().await {
            let send = match msg {
                WsOutbound::Text(t) => write.send(Message::Text(t)).await,
                WsOutbound::Pong(p) => write.send(Message::Pong(p)).await,
            };
            if send.is_err() {
                break;
            }
        }
    });

    loop {
        tokio::select! {
            _ = auth_tick.tick() => {
                let probes = auth::probe_local_cli_auth().await;
                let report = RelayMessage::AuthReport { cli_auth: probes };
                if outbound_tx.send(WsOutbound::Text(report.to_json()?)).await.is_err() {
                    break;
                }
            }
            inbound = read.next() => {
                let Some(msg) = inbound else { break };
                let msg = msg.context("websocket read")?;
                let text = match msg {
                    Message::Text(t) => t,
                    Message::Ping(p) => {
                        let _ = outbound_tx.send(WsOutbound::Pong(p)).await;
                        continue;
                    }
                    Message::Close(_) => break,
                    _ => continue,
                };

                let parsed = RelayMessage::from_json(&text).context("parse relay message")?;
                match parsed {
                    RelayMessage::Registered { relay_id, .. } => {
                        info!(%relay_id, "paired with server");
                    }
                    RelayMessage::RunJob {
                        job_id,
                        preset,
                        prompt,
                        friend_id,
                        group_id,
                        cwd,
                        cli_session_mode,
                        cli_session_id,
                        env,
                    } => {
                        let tx = outbound_tx.clone();
                        tokio::spawn(async move {
                            let (job_tx, mut job_rx) = mpsc::unbounded_channel();
                            let tx_forward = tx.clone();
                            let forward = tokio::spawn(async move {
                                while let Some(line) = job_rx.recv().await {
                                    if tx_forward
                                        .send(WsOutbound::Text(line))
                                        .await
                                        .is_err()
                                    {
                                        break;
                                    }
                                }
                            });
                            executor::run_job(
                                &job_id,
                                &preset,
                                &prompt,
                                friend_id.as_deref(),
                                group_id.as_deref(),
                                cwd.as_deref(),
                                cli_session_mode.as_deref(),
                                cli_session_id.as_deref(),
                                &env,
                                job_tx,
                            )
                            .await;
                            let _ = forward.await;
                            let _ = tx
                                .send(WsOutbound::Text(
                                    RelayMessage::AuthReport {
                                        cli_auth: auth::probe_local_cli_auth().await,
                                    }
                                    .to_json()
                                    .unwrap_or_default(),
                                ))
                                .await;
                        });
                    }
                    RelayMessage::Ping => {
                        let _ = outbound_tx
                            .send(WsOutbound::Text(
                                RelayMessage::Pong.to_json().unwrap_or_default(),
                            ))
                            .await;
                    }
                    RelayMessage::Error { message } => {
                        anyhow::bail!("server error: {message}");
                    }
                    _ => {}
                }
            }
        }
    }

    drop(outbound_tx);
    let _ = writer.await;

    Ok(())
}

enum WsOutbound {
    Text(String),
    Pong(Vec<u8>),
}

fn ensure_rustls_crypto_provider() -> Result<()> {
    use rustls::crypto::{aws_lc_rs, ring, CryptoProvider};
    if CryptoProvider::get_default().is_some() {
        return Ok(());
    }
    if ring::default_provider().install_default().is_ok()
        || aws_lc_rs::default_provider().install_default().is_ok()
    {
        return Ok(());
    }
    anyhow::bail!("failed to install rustls CryptoProvider for wss:// connections")
}

async fn connect_relay(
    url: &Url,
) -> Result<
    (
        tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
        tokio_tungstenite::tungstenite::handshake::client::Response,
    ),
> {
    let candidates = relay_connect_candidates(url);
    let mut last_err: Option<anyhow::Error> = None;
    for candidate in candidates {
        match tokio::time::timeout(
            std::time::Duration::from_secs(15),
            connect_async(candidate.as_str()),
        )
        .await
        {
            Ok(Ok(pair)) => return Ok(pair),
            Ok(Err(e)) => last_err = Some(anyhow::anyhow!("{e}")),
            Err(_) => last_err = Some(anyhow::anyhow!("连接超时（15s）")),
        }
    }
    let err = last_err.unwrap_or_else(|| anyhow::anyhow!("无可用地址"));
    let hint = relay_connect_hint(url, &err);
    Err(anyhow::anyhow!("无法连接 {url}。{hint}"))
}

/// 优先尝试 `wss://`（与配置为 `ws://` 且主机非本机 loopback 时）。
fn relay_connect_candidates(url: &Url) -> Vec<Url> {
    let mut out = Vec::new();
    if url.scheme() == "ws" {
        if let Some(wss) = ws_to_wss_url(url) {
            if prefer_wss_first(url) {
                out.push(wss);
            }
        }
    }
    out.push(url.clone());
    if url.scheme() == "wss" {
        if let Some(ws) = wss_to_ws_url(url) {
            out.push(ws);
        }
    }
    out
}

fn prefer_wss_first(url: &Url) -> bool {
    if url.scheme() == "wss" {
        return true;
    }
    let host = url.host_str().unwrap_or("");
    !matches!(host, "127.0.0.1" | "localhost" | "::1" | "[::1]")
}

fn ws_to_wss_url(url: &Url) -> Option<Url> {
    let mut wss = url.clone();
    wss.set_scheme("wss").ok()?;
    Some(wss)
}

fn wss_to_ws_url(url: &Url) -> Option<Url> {
    let mut ws = url.clone();
    ws.set_scheme("ws").ok()?;
    Some(ws)
}

fn relay_connect_hint(url: &Url, err: &impl std::fmt::Display) -> String {
    let msg = err.to_string();
    if (msg.contains("308") || msg.contains("301") || msg.contains("302")) && url.scheme() == "ws" {
        let host = url.host_str().unwrap_or("localhost");
        let port = url.port().map(|p| format!(":{p}")).unwrap_or_default();
        return format!("服务端要求 HTTPS，请改用 wss://{host}{port}/cli-relay");
    }
    format!("请确认服务端地址与全局设置中的 CLI 转发 WebSocket 一致。原始错误：{msg}")
}
