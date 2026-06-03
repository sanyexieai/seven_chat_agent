//! 服务端 CLI 中继中心：配对令牌、在线转发节点、任务下发。

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

use dashmap::DashMap;
use parking_lot::Mutex;
use tokio::sync::{mpsc, oneshot};
use uuid::Uuid;

use seven_chat_agent_cli::CliAuthProbe;
use seven_chat_agent_cli_relay_protocol::RelayMessage;

#[derive(Debug, Clone, serde::Serialize)]
pub struct RelayNodeInfo {
    pub relay_id: String,
    pub name: String,
    pub host_label: Option<String>,
    /// 转发端上报的工作区根目录（绝对路径）。
    pub workspace_root: Option<String>,
    /// 转发端本机探测的外部 CLI 登录状态（按 preset）。
    #[serde(default, skip_serializing_if = "std::collections::HashMap::is_empty")]
    pub cli_auth: std::collections::HashMap<String, CliAuthProbe>,
    pub online: bool,
    pub connected_at: String,
}

#[derive(Debug, Clone)]
pub struct RelayJobSpec {
    pub preset: String,
    pub prompt: String,
    pub friend_id: String,
    pub group_id: Option<String>,
    /// 群成员 binding.local_path 等显式覆盖；留空则由转发端按约定解析。
    pub cwd_override: Option<String>,
    pub cli_session_mode: Option<String>,
    pub cli_session_id: Option<String>,
    pub env: Vec<(String, String)>,
}

#[derive(Debug, Clone)]
pub struct RelayJobResult {
    pub text: String,
    pub cli_deltas: Vec<worker_bee_cli::CliBlockDelta>,
    pub exit_code: Option<i32>,
}

struct ActiveRelay {
    name: String,
    host_label: Option<String>,
    workspace_root: Option<String>,
    cli_auth: std::collections::HashMap<String, CliAuthProbe>,
    connected_at: chrono::DateTime<chrono::Utc>,
    outbound: mpsc::Sender<RelayMessage>,
}

struct PendingJob {
    accumulated: String,
    cli_deltas: Vec<worker_bee_cli::CliBlockDelta>,
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
                workspace_root: e.value().workspace_root.clone(),
                cli_auth: e.value().cli_auth.clone(),
                online: true,
                connected_at: e.value().connected_at.to_rfc3339(),
            })
            .collect()
    }

    pub fn node_name(&self, relay_id: &str) -> Option<String> {
        self.relays.get(relay_id).map(|r| r.name.clone())
    }

    pub fn auth_for_preset(&self, relay_id: &str, preset: &str) -> Option<CliAuthProbe> {
        self.relays
            .get(relay_id)?
            .cli_auth
            .get(preset)
            .cloned()
    }

    pub fn set_cli_auth(&self, relay_id: &str, probes: Vec<CliAuthProbe>) {
        if let Some(mut relay) = self.relays.get_mut(relay_id) {
            relay.cli_auth = probes
                .into_iter()
                .map(|p| (p.preset.clone(), p))
                .collect();
        }
    }

    /// 转发端约定的好友工作区路径（仅展示；实际目录由转发端创建）。
    pub fn workspace_path_for_friend(&self, relay_id: &str, friend_id: &str) -> Option<String> {
        let relay = self.relays.get(relay_id)?;
        let root = relay.workspace_root.as_deref()?.trim();
        if root.is_empty() {
            return None;
        }
        Some(format!(
            "{}/friends/{}",
            root.trim_end_matches('/'),
            friend_id.trim()
        ))
    }

    pub fn set_workspace_root(&self, relay_id: &str, workspace_root: String) {
        if let Some(mut relay) = self.relays.get_mut(relay_id) {
            relay.workspace_root = Some(workspace_root);
        }
    }

    pub fn register_connection(
        self: &Arc<Self>,
        pairing_token: String,
        name: String,
        host_label: Option<String>,
        workspace_root: Option<String>,
        cli_auth: Vec<CliAuthProbe>,
    ) -> Result<(String, mpsc::Receiver<RelayMessage>), String> {
        if !self.consume_pairing_token(&pairing_token) {
            return Err("配对码无效或已过期".into());
        }
        let relay_id = format!("relay_{}", Uuid::new_v4().simple());
        let (tx, rx) = mpsc::channel::<RelayMessage>(32);
        let auth_map = cli_auth
            .into_iter()
            .map(|p| (p.preset.clone(), p))
            .collect();
        self.relays.insert(
            relay_id.clone(),
            ActiveRelay {
                name,
                host_label,
                workspace_root,
                cli_auth: auth_map,
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
                cli_deltas: Vec::new(),
                result_tx,
            },
        );

        let run = RelayMessage::RunJob {
            job_id: job_id.clone(),
            preset: spec.preset,
            prompt: spec.prompt,
            friend_id: Some(spec.friend_id),
            group_id: spec.group_id,
            cwd: spec.cwd_override,
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
            cli_delta,
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
        if let Some(v) = cli_delta {
            if let Ok(parsed) = serde_json::from_value::<worker_bee_cli::CliBlockDelta>(v.clone()) {
                pending.cli_deltas.push(parsed);
            }
        }

        if !*done {
            return;
        }

        let accumulated = pending.accumulated.clone();
        let cli_deltas = pending.cli_deltas.clone();
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
            cli_deltas,
            exit_code: *exit_code,
        }));
    }
}
