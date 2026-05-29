use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::State;
use axum::response::IntoResponse;
use futures::{SinkExt, StreamExt};

use crate::state::AppState;

pub async fn ws_handler(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_socket(socket, state))
}

async fn handle_socket(socket: WebSocket, state: AppState) {
    let (mut sender, mut receiver) = socket.split();
    let mut bus = state.core.dispatcher.subscribe();

    let _ = sender
        .send(Message::Text(
            serde_json::json!({"type":"hello","ts": chrono::Utc::now().to_rfc3339()})
                .to_string(),
        ))
        .await;

    let push = async {
        loop {
            match bus.recv().await {
                Ok(ev) => {
                    let text = match serde_json::to_string(&ev) {
                        Ok(t) => t,
                        Err(_) => continue,
                    };
                    if sender.send(Message::Text(text)).await.is_err() {
                        break;
                    }
                }
                Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
                Err(_) => break,
            }
        }
    };

    let recv = async {
        while let Some(Ok(msg)) = receiver.next().await {
            if matches!(msg, Message::Close(_)) {
                break;
            }
        }
    };

    tokio::select! {
        _ = push => {},
        _ = recv => {},
    }
}
