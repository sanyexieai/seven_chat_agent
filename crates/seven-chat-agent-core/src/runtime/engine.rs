use std::sync::Arc;

use async_stream::stream;
use futures::stream::BoxStream;

use crate::agent::{AgentEvent, ChatContext, ProviderUsageInfo};
use crate::domain::Friend;
use crate::provider::ProviderRegistry;
use crate::store::SqliteStore;
use crate::Result;

use super::backends::ThinkBackend;
use super::config::RuntimeProfile;
use super::memory::MemoryService;
use super::tools::{parse_tool_call, ToolContext, ToolRegistry};

/// honeycomb Agent 运行时：记忆 + 工具循环 + Provider / CLI 推理后端。
pub struct AgentRuntime {
    memory: Arc<MemoryService>,
    providers: Arc<ProviderRegistry>,
}

impl AgentRuntime {
    pub fn new(store: Arc<SqliteStore>, providers: Arc<ProviderRegistry>) -> Self {
        let skills_dir =
            std::env::var("SEVEN_CHAT_AGENT_SKILLS_DIR").unwrap_or_else(|_| "data/skills".into());
        Self {
            memory: Arc::new(MemoryService::new(store, skills_dir)),
            providers,
        }
    }

    pub async fn run_turn(
        &self,
        friend: &Friend,
        profile: &RuntimeProfile,
        ctx: &ChatContext,
        prompt: String,
    ) -> Result<BoxStream<'static, AgentEvent>> {
        let extra = ctx
            .group_settings
            .as_ref()
            .and_then(|g| g.extra_system_prompt.clone());
        let recall_ctx = crate::memory_tier::recall_context_from_chat(ctx);
        let mut system = self
            .memory
            .build_system_prompt(friend, profile, &prompt, extra.as_deref(), &recall_ctx)
            .await?;

        let delegate_cli = profile.delegate_cli.as_ref().map(|c| c.preset.as_str());
        let tools = ToolRegistry::for_profile(delegate_cli, &profile.mcp_servers);
        system.push_str(&tools.tools_prompt_section());

        let workspace = profile
            .workspace_cwd
            .clone()
            .unwrap_or_else(|| ".".into());

        let inference_cli = match &profile.inference {
            super::config::InferenceBackend::ExternalCli(c) => Some(c),
            _ => None,
        };
        let tool_ctx = ToolContext {
            friend_id: friend.id.clone(),
            workspace_cwd: workspace.clone(),
            skills_dir: profile.skills_dir.clone(),
            cli_preset: inference_cli
                .map(|_| None)
                .unwrap_or_else(|| delegate_cli.map(String::from)),
            cli_cmd: inference_cli
                .and_then(|c| c.cmd.clone())
                .or_else(|| pty_cmd_from_friend(friend)),
            mcp_servers: profile.mcp_servers.clone(),
        };

        let vision = match &profile.inference {
            super::config::InferenceBackend::WorkerBee(w) => self
                .providers
                .get(&w.provider.provider_id)
                .map(|p| p.capabilities().vision)
                .unwrap_or(false),
            super::config::InferenceBackend::ExternalCli(_) => false,
        };
        let mut messages = self.memory.build_messages(friend, &ctx, system, &prompt, vision);
        let think = ThinkBackend::from_profile(friend, profile);

        let providers = self.providers.clone();
        let memory = self.memory.clone();
        let friend_clone = friend.clone();
        let profile_clone = profile.clone();
        let turn_id = ctx
            .history
            .last()
            .map(|m| m.turn_id.clone())
            .unwrap_or_else(|| "unknown".into());
        let conversation_id = ctx.conversation_id.clone();
        let prompt_post = prompt.clone();
        let max_rounds = profile.max_tool_rounds;

        let s = stream! {
            let mut full = String::new();
            let mut model_used: Option<String> = None;
            let mut tokens_in: i64 = 0;
            let mut tokens_out: i64 = 0;

            let mut done = false;
            for round in 0..max_rounds {
                if done {
                    break;
                }
                match think.think(&providers, &profile_clone, &messages).await {
                    Ok(step) => {
                        tokens_in += step.usage.prompt_tokens;
                        tokens_out += step.usage.completion_tokens;
                        model_used = Some(step.label);

                        if let Some(call) = parse_tool_call(&step.text) {
                            yield AgentEvent::Tool {
                                name: call.name.clone(),
                                payload: call.arguments.to_string(),
                            };
                            let result = match tools.dispatch(&tool_ctx, &call).await {
                                Ok(r) => r,
                                Err(e) => format!("tool error: {e}"),
                            };
                            messages.push(crate::provider::types::ChatMessage::assistant(
                                step.text,
                            ));
                            messages.push(crate::provider::types::ChatMessage::user(format!(
                                "[工具 {} 结果]\n{result}\n请根据结果继续；若已足够请直接回答用户。",
                                call.name
                            )));
                            if round + 1 >= max_rounds {
                                yield AgentEvent::Error("工具调用轮次已达上限".into());
                                return;
                            }
                            continue;
                        }

                        if !step.text.trim().is_empty() {
                            full = step.text.clone();
                            yield AgentEvent::Token(step.text);
                        }
                        done = true;
                    }
                    Err(e) => {
                        yield AgentEvent::Error(e.to_string());
                        return;
                    }
                }
            }
            if !done {
                yield AgentEvent::Error("未能生成回复".into());
                return;
            }

            yield AgentEvent::Done(ProviderUsageInfo {
                model: model_used,
                tokens_in,
                tokens_out,
            });

            let fid = friend_clone.id.clone();
            let pid = profile_clone.memory_provider_id.clone();
            let model = profile_clone.memory_model.clone();
            let key = profile_clone.memory_api_key_id.clone();
            tokio::spawn(async move {
                memory
                    .post_turn(
                        &fid,
                        &conversation_id,
                        &turn_id,
                        &prompt_post,
                        &full,
                        tokens_in,
                        tokens_out,
                        &pid,
                        &model,
                        key.as_deref(),
                        &providers,
                    )
                    .await;
            });
        };

        Ok(Box::pin(s))
    }
}

fn pty_cmd_from_friend(friend: &Friend) -> Option<String> {
    let cfg: crate::domain::PtyBackendConfig =
        serde_json::from_value(friend.backend_config.clone()).ok()?;
    if cfg.cmd.is_empty() {
        None
    } else {
        Some(cfg.cmd)
    }
}
