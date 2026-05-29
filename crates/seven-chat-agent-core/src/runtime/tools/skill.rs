use async_trait::async_trait;
use serde_json::Value;

use super::{Tool, ToolContext};
use crate::agent::assistant::skills::SkillLibrary;
use crate::Result;

pub struct SkillTool;

#[async_trait]
impl Tool for SkillTool {
    fn name(&self) -> &'static str {
        "skill"
    }

    fn description(&self) -> &'static str {
        "加载 SKILL.md 全文。arguments: {\"name\":\"技能名\"}"
    }

    async fn execute(&self, ctx: &ToolContext, args: &Value) -> Result<String> {
        let name = args
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim();
        if name.is_empty() {
            return Ok("skill: 缺少 name".into());
        }
        let mut lib = SkillLibrary::new(&ctx.skills_dir, ctx.friend_id.clone());
        lib.reload();
        match lib.get_by_name(name) {
            Some(sk) => Ok(format!(
                "# {}\n\n{}\n\n---\n{}",
                sk.name, sk.summary, sk.body
            )),
            None => Ok(format!("skill: 未找到 {name}")),
        }
    }
}
