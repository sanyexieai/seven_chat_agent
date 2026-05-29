//! Web ↔ 服务端 ↔ 转发程序 之间的 CLI 中继协议。

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum RelayMessage {
    /// 转发端 → 服务端：注册/配对
    Register {
        pairing_token: String,
        name: String,
        #[serde(default)]
        host_label: Option<String>,
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
