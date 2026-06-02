//! 在远程电脑上运行的 CLI 转发程序：连接服务端 WebSocket，接收 RunJob 并在本机调用 CLI。

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
    #[arg(long, env = "SEVEN_CHAT_AGENT_RELAY_URL", default_value = "ws://127.0.0.1:8080/cli-relay")]
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

    let (ws, response) = tokio::time::timeout(
        std::time::Duration::from_secs(15),
        connect_async(url.as_str()),
    )
    .await
    .map_err(|_| anyhow::anyhow!("连接超时（15s）"))?
    .with_context(|| {
        format!(
            "无法连接 {url}。请确认 server 已启动；开发模式请用后端地址 ws://127.0.0.1:18737/cli-relay（不要用未配置代理的 18738）"
        )
    })?;
    info!(status = %response.status(), "websocket connected");
    let (mut write, mut read) = ws.split();

    let register = RelayMessage::Register {
        pairing_token: args.pairing_token.clone(),
        name: args.name.clone(),
        host_label: std::env::var("COMPUTERNAME")
            .ok()
            .or_else(|| std::env::var("HOSTNAME").ok()),
        workspace_root: Some(workspace_root.clone()),
    };
    write
        .send(Message::Text(register.to_json()?))
        .await
        .context("send register")?;

    let (outbound_tx, mut outbound_rx) = mpsc::channel::<String>(64);

    loop {
        tokio::select! {
            inbound = read.next() => {
                let Some(msg) = inbound else { break };
                let msg = msg.context("websocket read")?;
                let text = match msg {
                    Message::Text(t) => t,
                    Message::Ping(p) => {
                        write.send(Message::Pong(p)).await.ok();
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
                            let outputs = executor::run_job_collect(
                                &job_id,
                                &preset,
                                &prompt,
                                friend_id.as_deref(),
                                group_id.as_deref(),
                                cwd.as_deref(),
                                cli_session_mode.as_deref(),
                                cli_session_id.as_deref(),
                                &env,
                            )
                            .await;
                            for line in outputs {
                                let _ = tx.send(line).await;
                            }
                        });
                    }
                    RelayMessage::Ping => {
                        let _ = outbound_tx
                            .send(RelayMessage::Pong.to_json().unwrap_or_default())
                            .await;
                    }
                    RelayMessage::Error { message } => {
                        anyhow::bail!("server error: {message}");
                    }
                    _ => {}
                }
            }
            out = outbound_rx.recv() => {
                match out {
                    Some(text) => {
                        if write.send(Message::Text(text)).await.is_err() {
                            break;
                        }
                    }
                    None => break,
                }
            }
        }
    }

    Ok(())
}
