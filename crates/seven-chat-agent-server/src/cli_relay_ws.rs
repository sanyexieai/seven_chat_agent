use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::State;
use axum::response::IntoResponse;
use futures::{SinkExt, StreamExt};
use seven_chat_agent_cli_relay_protocol::RelayMessage;

use crate::state::AppState;

pub async fn cli_relay_handler(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_cli_relay(socket, state))
}

async fn handle_cli_relay(socket: WebSocket, state: AppState) {
    let (mut sender, mut receiver) = socket.split();
    let hub = state.core.cli_relay.clone();

    let first = match receiver.next().await {
        Some(Ok(Message::Text(t))) => t,
        _ => return,
    };

    let register = match RelayMessage::from_json(&first) {
        Ok(RelayMessage::Register {
            pairing_token,
            name,
            host_label,
            workspace_root,
            cli_auth,
        }) => (pairing_token, name, host_label, workspace_root, cli_auth),
        Ok(_) => {
            let err = RelayMessage::Error {
                message: "首条消息必须是 register".into(),
            };
            let _ = sender
                .send(Message::Text(err.to_json().unwrap_or_default()))
                .await;
            return;
        }
        Err(e) => {
            let err = RelayMessage::Error {
                message: format!("invalid json: {e}"),
            };
            let _ = sender
                .send(Message::Text(err.to_json().unwrap_or_default()))
                .await;
            return;
        }
    };

    let (pairing_token, name, host_label, workspace_root, cli_auth) = register;
    let display_name = name.clone();
    let (relay_id, mut outbound_rx) = match hub.register_connection(
        pairing_token,
        name,
        host_label,
        workspace_root,
        cli_auth,
    ) {
        Ok(v) => v,
        Err(message) => {
            tracing::warn!(%message, "cli relay register rejected");
            let err = RelayMessage::Error { message };
            let _ = sender
                .send(Message::Text(err.to_json().unwrap_or_default()))
                .await;
            return;
        }
    };

    tracing::info!(%relay_id, name = %display_name, "cli relay node online");

    let registered = RelayMessage::Registered {
        relay_id: relay_id.clone(),
        server_time: chrono::Utc::now().to_rfc3339(),
    };
    if sender
        .send(Message::Text(
            registered.to_json().unwrap_or_default(),
        ))
        .await
        .is_err()
    {
        hub.unregister(&relay_id);
        return;
    }

    let hub_in = hub.clone();
    let relay_id_in = relay_id.clone();

    let (write_tx, mut write_rx) = tokio::sync::mpsc::unbounded_channel::<RelayWsWrite>();
    let writer = tokio::spawn(async move {
        while let Some(msg) = write_rx.recv().await {
            let ok = match msg {
                RelayWsWrite::Text(t) => sender.send(Message::Text(t)).await.is_ok(),
                RelayWsWrite::Pong(p) => sender.send(Message::Pong(p)).await.is_ok(),
            };
            if !ok {
                break;
            }
        }
    });

    loop {
        tokio::select! {
            inbound = receiver.next() => {
                match inbound {
                    Some(Ok(Message::Text(text))) => {
                        let parsed = match RelayMessage::from_json(&text) {
                            Ok(m) => m,
                            Err(_) => continue,
                        };
                        match &parsed {
                            RelayMessage::JobOutput { job_id, .. } => {
                                hub_in.on_job_output(job_id, &parsed);
                            }
                            RelayMessage::WorkspaceReport { workspace_root } => {
                                hub_in.set_workspace_root(&relay_id_in, workspace_root.clone());
                                tracing::info!(
                                    relay_id = %relay_id_in,
                                    %workspace_root,
                                    "cli relay workspace reported"
                                );
                            }
                            RelayMessage::AuthReport { cli_auth } => {
                                hub_in.set_cli_auth(&relay_id_in, cli_auth.clone());
                                tracing::debug!(
                                    relay_id = %relay_id_in,
                                    count = cli_auth.len(),
                                    "cli relay auth reported"
                                );
                            }
                            RelayMessage::Ping => {
                                let _ = write_tx.send(RelayWsWrite::Text(
                                    RelayMessage::Pong.to_json().unwrap_or_default(),
                                ));
                            }
                            _ => {}
                        }
                    }
                    Some(Ok(Message::Ping(p))) => {
                        let _ = write_tx.send(RelayWsWrite::Pong(p));
                    }
                    Some(Ok(Message::Close(_))) | None => break,
                    _ => {}
                }
            }
            run = outbound_rx.recv() => {
                match run {
                    Some(msg) => {
                        let text = match msg.to_json() {
                            Ok(t) => t,
                            Err(_) => continue,
                        };
                        if write_tx.send(RelayWsWrite::Text(text)).is_err() {
                            break;
                        }
                    }
                    None => break,
                }
            }
        }
    }

    drop(write_tx);
    let _ = writer.await;

    hub.unregister(&relay_id_in);
}

enum RelayWsWrite {
    Text(String),
    Pong(Vec<u8>),
}
