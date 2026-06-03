//! Web ↔ 服务端 ↔ 转发程序 之间的 CLI 中继协议。

use serde::{Deserialize, Serialize};
use seven_chat_agent_cli_protocol::CliAuthProbe;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum RelayMessage {
    /// 转发端 → 服务端：注册/配对
    Register {
        pairing_token: String,
        name: String,
        #[serde(default)]
        host_label: Option<String>,
        /// 转发端本机工作区根目录（绝对路径）；由转发程序自行决定。
        #[serde(default)]
        workspace_root: Option<String>,
        /// 转发端本机各外部 CLI 登录探测结果（注册时上报）。
        #[serde(default)]
        cli_auth: Vec<CliAuthProbe>,
    },
    /// 转发端 → 服务端：工作区根目录变更（可选，连接后更新）
    WorkspaceReport {
        workspace_root: String,
    },
    /// 转发端 → 服务端：本机 CLI 鉴权状态更新
    AuthReport {
        cli_auth: Vec<CliAuthProbe>,
    },
    /// 服务端 → 转发端：注册成功
    Registered {
        relay_id: String,
        server_time: String,
    },
    /// 服务端 → 转发端：执行一次 CLI
    RunJob {
        job_id: String,
        preset: String,
        prompt: String,
        /// 好友 id；转发端据此解析 `{workspace_root}/friends/{friend_id}`。
        #[serde(default)]
        friend_id: Option<String>,
        /// 群 id；转发端据此解析 `{workspace_root}/groups/{group_id}`（优先于 friend）。
        #[serde(default)]
        group_id: Option<String>,
        /// 显式 cwd 覆盖（群成员 binding.local_path 等）；留空则由转发端按约定解析。
        #[serde(default)]
        cwd: Option<String>,
        #[serde(default)]
        cli_session_mode: Option<String>,
        #[serde(default)]
        cli_session_id: Option<String>,
        #[serde(default)]
        env: Vec<(String, String)>,
    },
    /// 转发端 → 服务端：任务输出片段
    JobOutput {
        job_id: String,
        #[serde(default)]
        text_delta: Option<String>,
        /// Codex `--json` 结构化增量（与 `worker_bee_cli::CliBlockDelta` 同形）
        #[serde(default)]
        cli_delta: Option<serde_json::Value>,
        #[serde(default)]
        done: bool,
        #[serde(default)]
        exit_code: Option<i32>,
        #[serde(default)]
        error: Option<String>,
    },
    /// 双向心跳
    Ping,
    Pong,
    /// 服务端 → 转发端：错误说明
    Error { message: String },
}

impl RelayMessage {
    pub fn to_json(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string(self)
    }

    pub fn from_json(s: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(s)
    }
}
