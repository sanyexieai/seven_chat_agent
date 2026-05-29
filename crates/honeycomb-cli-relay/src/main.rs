//! 在远程电脑上运行的 CLI 转发程序：连接服务端 WebSocket，接收 RunJob 并在本机调用 CLI。

mod executor;

use anyhow::{Context, Result};
use clap::Parser;
use futures::{SinkExt, StreamExt};
use honeycomb_cli_relay_protocol::RelayMessage;
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::info;
use url::Url;

#[derive(Debug, Parser)]
#[command(name = "honeycomb-cli-relay", about = "Honeycomb CLI 转发程序（远程本机执行）")]
struct Args {
    /// 服务端 WebSocket 地址，例如 ws://127.0.0.1:8080/cli-relay
    #[arg(long, env = "HONEYCOMB_RELAY_URL", default_value = "ws://127.0.0.1:8080/cli-relay")]
    url: String,

    /// 在 Web 端生成的配对令牌
    #[arg(long, env = "HONEYCOMB_RELAY_PAIRING_TOKEN")]
    pairing_token: String,

    /// 本机节点显示名称
    #[arg(long, env = "HONEYCOMB_RELAY_NAME", default_value = "local-relay")]
    name: String,
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
    info!(%url, name = %args.name, "connecting to honeycomb cli relay");

    let (ws, _) = connect_async(url.as_str())
        .await
        .context("websocket connect failed")?;
    let (mut write, mut read) = ws.split();

    let register = RelayMessage::Register {
        pairing_token: args.pairing_token.clone(),
        name: args.name.clone(),
        host_label: std::env::var("COMPUTERNAME")
            .ok()
            .or_else(|| std::env::var("HOSTNAME").ok()),
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
