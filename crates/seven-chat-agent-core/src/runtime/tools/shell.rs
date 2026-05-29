use async_trait::async_trait;
use serde_json::Value;
use tokio::process::Command;

use super::{Tool, ToolContext};
use crate::Result;

pub struct ShellTool;

#[async_trait]
impl Tool for ShellTool {
    fn name(&self) -> &'static str {
        "shell"
    }

    fn description(&self) -> &'static str {
        "在工作区内执行 shell 命令。arguments: {\"command\":\"...\"}"
    }

    async fn execute(&self, ctx: &ToolContext, args: &Value) -> Result<String> {
        let command = args
            .get("command")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim();
        if command.is_empty() {
            return Ok("shell: 缺少 command".into());
        }
        let output = Command::new("sh")
            .arg("-lc")
            .arg(command)
            .current_dir(&ctx.workspace_cwd)
            .output()
            .await
            .map_err(crate::Error::Io)?;
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        let code = output.status.code().unwrap_or(-1);
        Ok(format!(
            "exit={code}\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"
        ))
    }
}
