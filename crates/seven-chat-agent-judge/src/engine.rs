use async_trait::async_trait;

use crate::context::JudgeRequest;
use crate::heuristic::{self, apply_routing_hints};
use crate::parse;
use crate::prompt::{build_llm_prompt, LLM_JUDGE_SYSTEM};
use crate::resolve::resolve_llm_target;
use crate::types::{JudgeMode, JudgeSource, Judgment};

/// LLM judge 由宿主（seven-chat-agent-core）注入，避免 judge crate 依赖 Provider。
#[derive(Debug, Clone)]
pub struct LlmJudgeInput {
    pub provider_id: String,
    pub model: String,
    pub api_key_id: Option<String>,
    pub system: String,
    pub user_prompt: String,
    pub max_tokens: Option<u32>,
}

#[async_trait]
pub trait LlmJudgePort: Send + Sync {
    async fn complete_json(&self, input: LlmJudgeInput) -> Result<String, String>;
}

pub struct JudgeEngine;

impl JudgeEngine {
    /// 按群级 `JudgeMode` 与成员上下文给出判断。
    pub async fn evaluate(
        req: &JudgeRequest,
        port: Option<&dyn LlmJudgePort>,
        env_provider: Option<&str>,
        registry_has: impl Fn(&str) -> bool,
    ) -> Judgment {
        let mode = req.group_judge.mode;
        match mode {
            JudgeMode::Heuristic => {
                let mut j = heuristic::evaluate(req);
                if j.source.is_none() {
                    j.source = Some(JudgeSource::Heuristic);
                }
                j
            }
            JudgeMode::Llm => {
                Self::evaluate_llm(req, port, env_provider, registry_has)
                    .await
                    .map(|mut j| {
                        j.source = Some(JudgeSource::Llm);
                        apply_routing_hints(&j, req)
                    })
                    .unwrap_or_else(|e| Judgment {
                        should_reply: false,
                        confidence: 0.0,
                        reason: Some(format!("LLM judge 失败: {e}")),
                        suggested_delay_ms: 0,
                        source: Some(JudgeSource::LlmFailed),
                    })
            }
            JudgeMode::Auto => {
                if let Ok(j) = Self::evaluate_llm(req, port, env_provider, registry_has).await {
                    if j.confidence > 0.0 || j.should_reply {
                        let mut out = apply_routing_hints(&j, req);
                        out.source = Some(JudgeSource::AutoLlm);
                        return out;
                    }
                }
                let mut j = heuristic::evaluate(req);
                j.source = Some(JudgeSource::AutoHeuristic);
                j
            }
        }
    }

    async fn evaluate_llm(
        req: &JudgeRequest,
        port: Option<&dyn LlmJudgePort>,
        env_provider: Option<&str>,
        registry_has: impl Fn(&str) -> bool,
    ) -> Result<Judgment, String> {
        let port = port.ok_or_else(|| "LLM judge 未注入".to_string())?;
        let member_llm_provider = req.group_judge.llm.provider_id.as_deref();
        let target = resolve_llm_target(
            &req.group_judge,
            member_llm_provider,
            env_provider,
            registry_has,
        )
        .ok_or_else(|| "未配置可用的 judge Provider".to_string())?;
        let raw = port
            .complete_json(LlmJudgeInput {
                provider_id: target.provider_id,
                model: target.model,
                api_key_id: target.api_key_id,
                system: LLM_JUDGE_SYSTEM.into(),
                user_prompt: build_llm_prompt(req),
                max_tokens: None,
            })
            .await?;
        Ok(parse::parse_llm_response(&raw))
    }
}
