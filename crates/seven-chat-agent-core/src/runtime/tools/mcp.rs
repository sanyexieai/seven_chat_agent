use async_trait::async_trait;
use serde_json::Value;

use super::{Tool, ToolContext};
use crate::Result;

/// MCP 工具占位：后续接 `rmcp` / stdio MCP 客户端。
pub struct McpTool;

#[async_trait]
impl Tool for McpTool {
    fn name(&self) -> &'static str {
        "mcp"
    }

    fn description(&self) -> &'static str {
        "调用 MCP 服务。arguments: {\"server\":\"名称\",\"tool\":\"工具名\",\"input\":{...}}"
    }

    async fn execute(&self, ctx: &ToolContext, args: &Value) -> Result<String> {
        let server = args
            .get("server")
            .and_then(|v| v.as_str())
            .unwrap_or(ctx.mcp_servers.first().map(|s| s.as_str()).unwrap_or(""));
        if server.is_empty() {
            return Ok(
                "mcp: 未配置 server。在 backend_config.runtime.mcp_servers 或环境变量中配置。"
                    .into(),
            );
        }
        let tool = args
            .get("tool")
            .and_then(|v| v.as_str())
            .unwrap_or("ping");
        Ok(format!(
            "mcp: 客户端尚未接入（server={server}, tool={tool}）。\
             已登记的服务器：{:?}",
            ctx.mcp_servers
        ))
    }
}
