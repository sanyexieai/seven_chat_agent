use std::sync::Arc;

use async_trait::async_trait;
use dashmap::DashMap;

use crate::domain::{Provider, ProviderCapabilities, ProviderPrice};
use crate::provider::anthropic::AnthropicProvider;
use crate::provider::gemini::GeminiProvider;
use crate::provider::ollama::OllamaProvider;
use crate::provider::openai_compat::{KeyMaterial, KeyResolver, OpenAiCompatProvider};
use crate::provider::rate_limit::RateLimiter;
use crate::provider::types::ProviderUsage;
use crate::provider::ModelProvider;
use crate::store::SqliteStore;
use crate::Result;

pub type ProviderHandle = Arc<dyn ModelProvider>;

pub struct ProviderRegistry {
    store: Arc<SqliteStore>,
    handles: DashMap<String, ProviderHandle>,
    rate: Arc<RateLimiter>,
}

impl ProviderRegistry {
    pub async fn new(store: Arc<SqliteStore>) -> Result<Self> {
        seed_default_providers(&store).await?;
        let reg = Self {
            store: store.clone(),
            handles: DashMap::new(),
            rate: Arc::new(RateLimiter::new()),
        };
        reg.reload().await?;
        Ok(reg)
    }

    pub async fn reload(&self) -> Result<()> {
        let providers = self.store.list_providers().await?;
        self.handles.clear();
        for p in providers {
            if !p.enabled {
                continue;
            }
            let handle = self.build_handle(p.clone())?;
            self.handles.insert(p.id.clone(), handle);
        }
        Ok(())
    }

    pub fn get(&self, provider_id: &str) -> Option<ProviderHandle> {
        self.handles.get(provider_id).map(|v| v.clone())
    }

    pub fn list(&self) -> Vec<ProviderHandle> {
        self.handles.iter().map(|e| e.value().clone()).collect()
    }

    /// 解析某 Provider 的 API Key（vault 优先，否则 `{PROVIDER_ID}_API_KEY` 环境变量）。
    pub async fn resolve_provider_secret(
        &self,
        provider_id: &str,
        api_key_id: Option<&str>,
    ) -> Result<Option<String>> {
        if let Some(id) = api_key_id {
            if let Some(k) = self.store.get_provider_key(id).await? {
                if k.status == "active" {
                    if let Some(s) = self.store.vault.get(&k.secret_ref) {
                        return Ok(Some(s));
                    }
                }
            }
        }
        let keys = self.store.list_provider_keys(Some(provider_id)).await?;
        for k in keys {
            if k.status == "active" {
                if let Some(s) = self.store.vault.get(&k.secret_ref) {
                    return Ok(Some(s));
                }
            }
        }
        let env_name = crate::runtime::env_api_key_var(provider_id);
        Ok(std::env::var(env_name).ok().filter(|s| !s.trim().is_empty()))
    }

    fn build_handle(&self, p: Provider) -> Result<ProviderHandle> {
        let resolver: Arc<dyn KeyResolver> = Arc::new(StoreKeyResolver {
            store: self.store.clone(),
            rate: self.rate.clone(),
        });
        match p.kind.as_str() {
            "anthropic" => Ok(Arc::new(AnthropicProvider::new(
                p,
                self.store.vault.clone(),
                resolver,
            ))),
            "gemini" => Ok(Arc::new(GeminiProvider::new(
                p,
                self.store.vault.clone(),
                resolver,
            ))),
            "ollama" => Ok(Arc::new(OllamaProvider::new(p, resolver))),
            _ => Ok(Arc::new(OpenAiCompatProvider::new(
                p,
                self.store.vault.clone(),
                resolver,
            ))),
        }
    }
}

struct StoreKeyResolver {
    store: Arc<SqliteStore>,
    rate: Arc<RateLimiter>,
}

#[async_trait]
impl KeyResolver for StoreKeyResolver {
    async fn resolve(&self, provider_id: &str, hint: Option<&str>) -> Result<Option<KeyMaterial>> {
        let pick = self.pick_active_key(provider_id, hint).await?;
        if let Some(k) = pick {
            self.rate.acquire(&k.id, k.rpm_limit).await?;
            if let Some(secret) = self.store.vault.get(&k.secret_ref) {
                return Ok(Some(KeyMaterial {
                    key_id: k.id,
                    secret,
                }));
            }
        }
        Ok(None)
    }

    async fn record_usage(&self, key_id: &str, usage: &ProviderUsage) -> Result<()> {
        let key = self.store.get_provider_key(key_id).await?;
        let provider = if let Some(k) = &key {
            self.store.get_provider(&k.provider_id).await?
        } else {
            None
        };
        let (pi, po) = provider
            .map(|p| (p.price.input_per_mtok, p.price.output_per_mtok))
            .unwrap_or((0.0, 0.0));
        self.store
            .record_usage(key_id, usage.prompt_tokens, usage.completion_tokens, pi, po)
            .await
    }
}

impl StoreKeyResolver {
    async fn pick_active_key(
        &self,
        provider_id: &str,
        hint: Option<&str>,
    ) -> Result<Option<crate::domain::ProviderKey>> {
        if let Some(id) = hint {
            if let Some(k) = self.store.get_provider_key(id).await? {
                if k.status == "active" {
                    return Ok(Some(k));
                }
            }
        }
        let keys = self.store.list_provider_keys(Some(provider_id)).await?;
        for k in keys {
            if k.status == "active" {
                return Ok(Some(k));
            }
        }
        Ok(None)
    }
}

async fn seed_default_providers(store: &SqliteStore) -> Result<()> {
    let now = || chrono::Utc::now();
    let defaults = vec![
        Provider {
            id: "openai".into(),
            kind: "openai_compat".into(),
            display_name: "OpenAI".into(),
            base_url: "https://api.openai.com/v1".into(),
            default_model: Some("gpt-4o-mini".into()),
            capabilities: ProviderCapabilities {
                stream: true,
                tools: true,
                vision: true,
                thinking: false,
                context_len: 128_000,
                embeddings: true,
            },
            price: ProviderPrice {
                input_per_mtok: 0.15,
                output_per_mtok: 0.60,
            },
            enabled: true,
            created_at: now(),
        },
        Provider {
            id: "anthropic".into(),
            kind: "anthropic".into(),
            display_name: "Anthropic Claude".into(),
            base_url: "https://api.anthropic.com".into(),
            default_model: Some("claude-3-7-sonnet-latest".into()),
            capabilities: ProviderCapabilities {
                stream: true,
                tools: true,
                vision: true,
                thinking: true,
                context_len: 200_000,
                embeddings: false,
            },
            price: ProviderPrice {
                input_per_mtok: 3.0,
                output_per_mtok: 15.0,
            },
            enabled: true,
            created_at: now(),
        },
        Provider {
            id: "gemini".into(),
            kind: "gemini".into(),
            display_name: "Google Gemini".into(),
            base_url: "https://generativelanguage.googleapis.com/v1beta".into(),
            default_model: Some("gemini-2.0-flash".into()),
            capabilities: ProviderCapabilities {
                stream: true,
                tools: true,
                vision: true,
                thinking: false,
                context_len: 1_000_000,
                embeddings: true,
            },
            price: ProviderPrice {
                input_per_mtok: 0.1,
                output_per_mtok: 0.4,
            },
            enabled: true,
            created_at: now(),
        },
        Provider {
            id: "deepseek".into(),
            kind: "openai_compat".into(),
            display_name: "DeepSeek".into(),
            base_url: "https://api.deepseek.com/v1".into(),
            default_model: Some("deepseek-chat".into()),
            capabilities: ProviderCapabilities {
                stream: true,
                tools: true,
                vision: false,
                thinking: true,
                context_len: 64_000,
                embeddings: false,
            },
            price: ProviderPrice {
                input_per_mtok: 0.27,
                output_per_mtok: 1.10,
            },
            enabled: true,
            created_at: now(),
        },
        Provider {
            id: "qwen".into(),
            kind: "openai_compat".into(),
            display_name: "通义千问".into(),
            base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1".into(),
            default_model: Some("qwen-plus".into()),
            capabilities: ProviderCapabilities {
                stream: true,
                tools: true,
                vision: true,
                thinking: false,
                context_len: 128_000,
                embeddings: true,
            },
            price: ProviderPrice::default(),
            enabled: true,
            created_at: now(),
        },
        Provider {
            id: "moonshot".into(),
            kind: "openai_compat".into(),
            display_name: "Moonshot Kimi".into(),
            base_url: "https://api.moonshot.cn/v1".into(),
            default_model: Some("moonshot-v1-8k".into()),
            capabilities: ProviderCapabilities {
                stream: true,
                tools: true,
                vision: false,
                thinking: false,
                context_len: 128_000,
                embeddings: false,
            },
            price: ProviderPrice::default(),
            enabled: true,
            created_at: now(),
        },
        Provider {
            id: "openrouter".into(),
            kind: "openai_compat".into(),
            display_name: "OpenRouter".into(),
            base_url: "https://openrouter.ai/api/v1".into(),
            default_model: Some("openai/gpt-4o-mini".into()),
            capabilities: ProviderCapabilities {
                stream: true,
                tools: true,
                vision: true,
                thinking: false,
                context_len: 200_000,
                embeddings: false,
            },
            price: ProviderPrice::default(),
            enabled: true,
            created_at: now(),
        },
        Provider {
            id: "ollama".into(),
            kind: "ollama".into(),
            display_name: "Ollama".into(),
            base_url: "http://localhost:11434".into(),
            default_model: Some("llama3.2".into()),
            capabilities: ProviderCapabilities {
                stream: true,
                tools: false,
                vision: false,
                thinking: false,
                context_len: 8_192,
                embeddings: false,
            },
            price: ProviderPrice::default(),
            enabled: true,
            created_at: now(),
        },
        Provider {
            id: "lmstudio".into(),
            kind: "openai_compat".into(),
            display_name: "LM Studio".into(),
            base_url: "http://localhost:1234/v1".into(),
            default_model: None,
            capabilities: ProviderCapabilities {
                stream: true,
                tools: false,
                vision: false,
                thinking: false,
                context_len: 8_192,
                embeddings: false,
            },
            price: ProviderPrice::default(),
            enabled: true,
            created_at: now(),
        },
        Provider {
            id: "vllm".into(),
            kind: "openai_compat".into(),
            display_name: "vLLM".into(),
            base_url: "http://localhost:8000/v1".into(),
            default_model: None,
            capabilities: ProviderCapabilities {
                stream: true,
                tools: false,
                vision: false,
                thinking: false,
                context_len: 32_768,
                embeddings: false,
            },
            price: ProviderPrice::default(),
            enabled: true,
            created_at: now(),
        },
    ];
    for p in defaults {
        if store.get_provider(&p.id).await?.is_none() {
            store.upsert_provider(&p).await?;
        }
    }
    Ok(())
}
