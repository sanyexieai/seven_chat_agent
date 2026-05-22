use std::path::Path;

use anyhow::Result;
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
pub struct McpServerRef {
    pub name: String,
    pub command: Option<String>,
}

/// 从 `{data_dir}/mcp.json` 读取 MCP 服务列表（占位，后续接真实客户端）。
pub fn load_servers(data_dir: &Path) -> Result<Vec<McpServerRef>> {
    let path = data_dir.join("mcp.json");
    if !path.exists() {
        return Ok(Vec::new());
    }
    let raw = std::fs::read_to_string(&path)?;
    let list: Vec<McpServerRef> = serde_json::from_str(&raw).unwrap_or_default();
    Ok(list)
}

pub fn format_mcp_block(servers: &[McpServerRef]) -> String {
    if servers.is_empty() {
        return String::new();
    }
    let mut s = String::from("\n\n[MCP 服务]\n");
    for srv in servers {
        s.push_str(&format!(
            "- {}{}\n",
            srv.name,
            srv.command
                .as_ref()
                .map(|c| format!(" ({c})"))
                .unwrap_or_default()
        ));
    }
    s
}
