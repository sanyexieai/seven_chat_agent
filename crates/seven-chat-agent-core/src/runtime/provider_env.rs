//! 工蜂实例 API 配置为空时，从环境变量解析 Provider / Model / Key。

use tracing::info;

use super::config::ProviderInferenceConfig;

/// 内置 Provider id 顺序（与 `.env.example` 一致）；用于「仅配置了某家 Key」时自动选型。
const PROVIDER_DETECT_ORDER: &[&str] = &[
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "qwen",
    "moonshot",
    "openrouter",
    "ollama",
    "lmstudio",
    "vllm",
];

/// `{PROVIDER_ID}_API_KEY` 环境变量名。
pub fn env_api_key_var(provider_id: &str) -> String {
    format!(
        "{}_API_KEY",
        provider_id.to_uppercase().replace('-', "_")
    )
}

/// 该 Provider 是否在环境变量中配置了非空 API Key。
pub fn env_has_provider_key(provider_id: &str) -> bool {
    std::env::var(env_api_key_var(provider_id))
        .ok()
        .map(|s| !s.trim().is_empty())
        .unwrap_or(false)
}

/// 扫描环境变量，返回第一个配置了 `{ID}_API_KEY` 的 Provider id。
pub fn detect_provider_id_from_env() -> Option<String> {
    PROVIDER_DETECT_ORDER
        .iter()
        .find(|id| env_has_provider_key(id))
        .map(|s| (*s).to_string())
}

fn env_nonempty(key: &str) -> Option<String> {
    std::env::var(key)
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

fn default_model_for_provider(provider_id: &str) -> &'static str {
    match provider_id {
        "anthropic" => "claude-sonnet-4-20250514",
        "gemini" => "gemini-2.0-flash",
        "deepseek" => "deepseek-chat",
        "qwen" => "qwen-plus",
        "moonshot" => "moonshot-v1-8k",
        "openrouter" => "openai/gpt-4o-mini",
        "ollama" => "llama3.2",
        "lmstudio" => "local-model",
        "vllm" => "local-model",
        _ => "gpt-4o-mini",
    }
}

/// 将工蜂实例的 Provider 配置与 `.env` / 进程环境对齐（`backend_config` 字段为空时）。
pub fn resolve_worker_bee_provider(
    provider_id: &str,
    model: &str,
    api_key_id: Option<String>,
) -> ProviderInferenceConfig {
    let explicit_pid = provider_id.trim();
    let explicit_model = model.trim();

    let (pid, pid_from_env) = if !explicit_pid.is_empty() {
        (explicit_pid.to_string(), false)
    } else if let Some(v) = env_nonempty("WORKER_BEE_PROVIDER_ID") {
        (v, true)
    } else if let Some(v) = env_nonempty("SEVEN_CHAT_AGENT_ASSISTANT_PROVIDER") {
        (v, true)
    } else if let Some(v) = detect_provider_id_from_env() {
        info!(
            provider_id = %v,
            "worker bee: provider_id empty, detected from env API key"
        );
        (v, true)
    } else {
        (
            "openai".to_string(),
            true,
        )
    };

    let (mdl, mdl_from_env) = if !explicit_model.is_empty() {
        (explicit_model.to_string(), false)
    } else if let Some(v) = env_nonempty("WORKER_BEE_MODEL") {
        (v, true)
    } else if let Some(v) = env_nonempty("SEVEN_CHAT_AGENT_ASSISTANT_MODEL") {
        (v, true)
    } else {
        let d = default_model_for_provider(&pid);
        if pid_from_env {
            info!(
                provider_id = %pid,
                model = %d,
                "worker bee: model empty, using default for provider"
            );
        }
        (d.to_string(), true)
    };

    if pid_from_env && explicit_pid.is_empty() {
        info!(
            provider_id = %pid,
            model = %mdl,
            api_key_id = ?api_key_id,
            "worker bee: loaded API config from environment"
        );
    } else if mdl_from_env && explicit_model.is_empty() {
        info!(
            provider_id = %pid,
            model = %mdl,
            "worker bee: model loaded from environment"
        );
    }

    ProviderInferenceConfig {
        provider_id: pid,
        model: mdl,
        api_key_id,
        model_chain: vec![],
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn explicit_config_unchanged() {
        let c = resolve_worker_bee_provider("deepseek", "deepseek-chat", None);
        assert_eq!(c.provider_id, "deepseek");
        assert_eq!(c.model, "deepseek-chat");
    }

    #[test]
    fn env_var_name_format() {
        assert_eq!(env_api_key_var("openrouter"), "OPENROUTER_API_KEY");
        assert_eq!(env_api_key_var("lm-studio"), "LM_STUDIO_API_KEY");
    }
}
