//! 服务端 CLI 中继中心：配对令牌、在线转发节点、任务下发。

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

use dashmap::DashMap;
use parking_lot::Mutex;
use tokio::sync::{mpsc, oneshot};
use uuid::Uuid;

use seven_chat_agent_cli_relay_protocol::RelayMessage;

#[derive(Debug, Clone, serde::Serialize)]
pub struct RelayNodeInfo {
    pub relay_id: String,
    pub name: String,
    pub host_label: Option<String>,
    pub online: bool,
    pub connected_at: String,
}

#[derive(Debug, Clone)]
pub struct RelayJobSpec {
    pub preset: String,
    pub prompt: String,
    pub cwd: Option<String>,
    pub cli_session_mode: Option<String>,
    pub cli_session_id: Option<String>,
    pub env: Vec<(String, String)>,
}

#[derive(Debug, Clone)]
pub struct RelayJobResult {
    pub text: String,
    pub exit_code: Option<i32>,
}

struct ActiveRelay {
    name: String,
    host_label: Option<String>,
    connected_at: chrono::DateTime<chrono::Utc>,
    outbound: mpsc::Sender<RelayMessage>,
}

struct PendingJob {
    accumulated: String,
    result_tx: oneshot::Sender<Result<RelayJobResult, String>>,
}

pub struct RelayHub {
    relays: DashMap<String, ActiveRelay>,
    pairing_tokens: Mutex<HashMap<String, Instant>>,
    jobs: DashMap<String, PendingJob>,
}

impl RelayHub {
    pub fn new() -> Arc<Self> {
        Arc::new(Self {
            relays: DashMap::new(),
            pairing_tokens: Mutex::new(HashMap::new()),
            jobs: DashMap::new(),
        })
    }

    /// 在 Web 端生成一次性配对码（默认 15 分钟有效）。
    pub fn create_pairing_token(self: &Arc<Self>) -> String {
        let token = format!("pair_{}", Uuid::new_v4().simple());
        self.pairing_tokens
            .lock()
            .insert(token.clone(), Instant::now());
        token
    }

    fn consume_pairing_token(&self, token: &str) -> bool {
        let mut map = self.pairing_tokens.lock();
        let Some(created) = map.remove(token) else {
            return false;
        };
        created.elapsed() < Duration::from_secs(15 * 60)
    }

    pub fn list_nodes(&self) -> Vec<RelayNodeInfo> {
        self.relays
            .iter()
            .map(|e| RelayNodeInfo {
                relay_id: e.key().clone(),
                name: e.value().name.clone(),
                host_label: e.value().host_label.clone(),
                online: true,
                connected_at: e.value().connected_at.to_rfc3339(),
            })
            .collect()
    }

    pub fn register_connection(
        self: &Arc<Self>,
        pairing_token: String,
        name: String,
        host_label: Option<String>,
    ) -> Result<(String, mpsc::Receiver<RelayMessage>), String> {
        if !self.consume_pairing_token(&pairing_token) {
            return Err("配对码无效或已过期".into());
        }
        let relay_id = format!("relay_{}", Uuid::new_v4().simple());
        let (tx, rx) = mpsc::channel::<RelayMessage>(32);
        self.relays.insert(
            relay_id.clone(),
            ActiveRelay {
                name,
                host_label,
                connected_at: chrono::Utc::now(),
                outbound: tx,
            },
        );
        Ok((relay_id, rx))
    }

    pub fn unregister(&self, relay_id: &str) {
        self.relays.remove(relay_id);
    }

    pub fn is_online(&self, relay_id: &str) -> bool {
        self.relays.contains_key(relay_id)
    }

    pub async fn run_job(
        self: &Arc<Self>,
        relay_id: &str,
        spec: RelayJobSpec,
        timeout: Duration,
    ) -> Result<RelayJobResult, String> {
        let relay = self
            .relays
            .get(relay_id)
            .ok_or_else(|| format!("转发节点 {relay_id} 未在线"))?;
        let job_id = format!("job_{}", Uuid::new_v4().simple());
        let (result_tx, result_rx) = oneshot::channel();
        self.jobs.insert(
            job_id.clone(),
            PendingJob {
                accumulated: String::new(),
                result_tx,
            },
        );

        let run = RelayMessage::RunJob {
            job_id: job_id.clone(),
            preset: spec.preset,
            prompt: spec.prompt,
            cwd: spec.cwd,
            cli_session_mode: spec.cli_session_mode,
            cli_session_id: spec.cli_session_id,
            env: spec.env,
        };
        relay
            .outbound
            .send(run)
            .await
            .map_err(|_| "转发连接已断开".to_string())?;

        let result = tokio::time::timeout(timeout, result_rx)
            .await
            .map_err(|_| "CLI 转发任务超时".to_string())?
            .map_err(|_| "CLI 转发任务被取消".to_string())??;

        self.jobs.remove(&job_id);
        Ok(result)
    }

    pub fn on_job_output(&self, job_id: &str, msg: &RelayMessage) {
        let RelayMessage::JobOutput {
            text_delta,
            done,
            exit_code,
            error,
            ..
        } = msg
        else {
            return;
        };

        let Some(mut pending) = self.jobs.get_mut(job_id) else {
            return;
        };

        if let Some(delta) = text_delta {
            pending.accumulated.push_str(delta);
        }

        if !*done {
            return;
        }

        let accumulated = pending.accumulated.clone();
        drop(pending);

        let Some((_, pending)) = self.jobs.remove(job_id) else {
            return;
        };

        if let Some(err) = error {
            let _ = pending.result_tx.send(Err(err.clone()));
            return;
        }

        let _ = pending.result_tx.send(Ok(RelayJobResult {
            text: accumulated,
            exit_code: *exit_code,
        }));
    }
}
