//! 转发端本机外部 CLI 登录状态探测（上报服务端供 Web 展示）。

use seven_chat_agent_cli::{
    ensure_executable, probe_auth, CliLaunchConfig, EXTERNAL_CLI_PRESETS,
};
use seven_chat_agent_cli_protocol::CliAuthProbe;

/// 探测本机已安装的外部 CLI（claude / codex / cursor）登录状态。
pub async fn probe_local_cli_auth() -> Vec<CliAuthProbe> {
    let mut out = Vec::new();
    for &preset in EXTERNAL_CLI_PRESETS {
        let launch = CliLaunchConfig {
            preset: preset.to_string(),
            cmd: String::new(),
            cli_session_mode: None,
            cli_session_id: None,
            cli_sandbox_mode: None,
        };
        let cmd = match ensure_executable(preset, &launch) {
            Ok(c) => c,
            Err(e) => {
                out.push(CliAuthProbe {
                    preset: preset.to_string(),
                    authenticated: false,
                    detail: e.to_string(),
                    api_key_configured: false,
                });
                continue;
            }
        };
        out.push(probe_auth(preset, &cmd, false).await);
    }
    out
}
