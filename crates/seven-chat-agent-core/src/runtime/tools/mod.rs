mod cli;
mod mcp;
mod shell;
mod skill;

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub use cli::CliTool;
pub use mcp::McpTool;
pub use shell::ShellTool;
pub use skill::SkillTool;

use crate::Result;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub name: String,
    pub arguments: Value,
}

#[derive(Debug, Clone)]
pub struct ToolContext {
    pub friend_id: String,
    pub workspace_cwd: String,
    pub skills_dir: String,
    pub cli_preset: Option<String>,
    /// preset=custom 时的可执行文件名。
    pub cli_cmd: Option<String>,
    pub mcp_servers: Vec<String>,
}

#[async_trait]
pub trait Tool: Send + Sync {
    fn name(&self) -> &'static str;
    fn description(&self) -> &'static str;
    async fn execute(&self, ctx: &ToolContext, args: &Value) -> Result<String>;
}

pub struct ToolRegistry {
    tools: Vec<Box<dyn Tool>>,
}

impl ToolRegistry {
    pub fn for_profile(cli_preset: Option<&str>, mcp_servers: &[String]) -> Self {
        let mut tools: Vec<Box<dyn Tool>> = vec![
            Box::new(ShellTool),
            Box::new(SkillTool),
        ];
        if cli_preset.is_some() {
            tools.push(Box::new(CliTool));
        }
        if !mcp_servers.is_empty() {
            tools.push(Box::new(McpTool));
        }
        Self { tools }
    }

    pub fn list(&self) -> Vec<(&'static str, &'static str)> {
        self.tools
            .iter()
            .map(|t| (t.name(), t.description()))
            .collect()
    }

    pub async fn dispatch(&self, ctx: &ToolContext, call: &ToolCall) -> Result<String> {
        for t in &self.tools {
            if t.name() == call.name {
                return t.execute(ctx, &call.arguments).await;
            }
        }
        Ok(format!("未知工具：{}", call.name))
    }

    pub fn tools_prompt_section(&self) -> String {
        let mut s = String::from(
            "\n\n[工具] 需要外部能力时，先只输出一行 JSON（不要 markdown）：\n\
             {\"tool_call\":{\"name\":\"<工具名>\",\"arguments\":{...}}}\n\
             收到工具结果后会继续对话；最终给用户的答案用正常中文，不要包在 JSON 里。\n\
             可用工具：\n",
        );
        for (name, desc) in self.list() {
            s.push_str(&format!("- {name}: {desc}\n"));
        }
        s
    }
}

pub fn parse_tool_call(text: &str) -> Option<ToolCall> {
    let trimmed = text.trim();
    if let Ok(v) = serde_json::from_str::<Value>(trimmed) {
        if let Some(tc) = v.get("tool_call") {
            return parse_tool_value(tc);
        }
        if v.get("name").is_some() {
            return parse_tool_value(&v);
        }
    }
    if let Some(start) = trimmed.find("{\"tool_call\"") {
        if let Some(obj) = extract_json_object(&trimmed[start..]) {
            if let Ok(v) = serde_json::from_str::<Value>(&obj) {
                if let Some(tc) = v.get("tool_call") {
                    return parse_tool_value(tc);
                }
            }
        }
    }
    None
}

fn parse_tool_value(v: &Value) -> Option<ToolCall> {
    let name = v.get("name")?.as_str()?.to_string();
    let arguments = v.get("arguments").cloned().unwrap_or(Value::Object(Default::default()));
    Some(ToolCall { name, arguments })
}

fn extract_json_object(s: &str) -> Option<String> {
    let start = s.find('{')?;
    let mut depth = 0i32;
    for (i, c) in s[start..].char_indices() {
        match c {
            '{' => depth += 1,
            '}' => {
                depth -= 1;
                if depth == 0 {
                    return Some(s[start..start + i + 1].to_string());
                }
            }
            _ => {}
        }
    }
    None
}
