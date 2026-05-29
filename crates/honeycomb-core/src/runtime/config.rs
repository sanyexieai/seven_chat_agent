use serde::Deserialize;

use crate::cli_workspace;
use crate::domain::{
    ApiBackendConfig, ApiModelRef, ApiSamplingParams, AssistantBackendConfig, BackendKind,
    Friend,
    PtyBackendConfig,
};
use crate::friend_cli::{is_external_cli_preset, pty_preset_is_worker_bee, resolve_pty_preset};
use crate::runtime::provider_env::resolve_worker_bee_provider;
use crate::runtime::WORKER_BEE_CLI_PRESET;

/// Agent 运行时推理：外部 CLI 直通，或工蜂 CLI 实例（API 配置挂在工蜂下）。
#[derive(Debug, Clone)]
pub enum InferenceBackend {
    /// 本机外部 CLI（claude / codex-exec …），不经服务端 Provider 推理。
    ExternalCli(CliInferenceConfig),
    /// 工蜂 CLI 实例；`provider` 为该实例选用的平台 API（可多个好友 = 多个实例）。
    WorkerBee(WorkerBeeInferenceConfig),
}

#[derive(Debug, Clone)]
pub struct WorkerBeeInferenceConfig {
    pub instance_id: String,
    pub provider: ProviderInferenceConfig,
    pub skills_dir: String,
    pub memory_top_k: usize,
}

#[derive(Debug, Clone)]
pub struct ProviderInferenceConfig {
    pub provider_id: String,
    pub model: String,
    pub api_key_id: Option<String>,
    pub model_chain: Vec<ApiModelRef>,
}

impl ProviderInferenceConfig {
    pub fn with_model_chain(mut self, chain: Vec<ApiModelRef>) -> Self {
        if !chain.is_empty() {
            self.model_chain = chain;
        }
        self
    }
}

#[derive(Debug, Clone)]
pub struct CliInferenceConfig {
    pub preset: String,
    pub cmd: Option<String>,
}

#[derive(Debug, Clone)]
pub struct RuntimeProfile {
    pub inference: InferenceBackend,
    pub delegate_cli: Option<CliInferenceConfig>,
    pub params: ApiSamplingParams,
    pub memory_top_k: usize,
    pub skills_dir: String,
    pub mcp_servers: Vec<String>,
    pub workspace_cwd: Option<String>,
    pub max_tool_rounds: usize,
    pub temperature: f32,
    pub max_tokens: u32,
    pub memory_provider_id: String,
    pub memory_model: String,
    pub memory_api_key_id: Option<String>,
}

impl Default for RuntimeProfile {
    fn default() -> Self {
        let prov = ProviderInferenceConfig {
            provider_id: std::env::var("HONEYCOMB_ASSISTANT_PROVIDER")
                .unwrap_or_else(|_| "openai".into()),
            model: std::env::var("HONEYCOMB_ASSISTANT_MODEL")
                .unwrap_or_else(|_| "gpt-4o-mini".into()),
            api_key_id: None,
            model_chain: vec![],
        };
        Self {
            inference: InferenceBackend::WorkerBee(WorkerBeeInferenceConfig {
                instance_id: "default".into(),
                provider: prov.clone(),
                skills_dir: "data/skills".into(),
                memory_top_k: 5,
            }),
            delegate_cli: None,
            params: ApiSamplingParams::default(),
            memory_top_k: 5,
            skills_dir: "data/skills".into(),
            mcp_servers: vec![],
            workspace_cwd: None,
            max_tool_rounds: 6,
            temperature: 0.5,
            max_tokens: 2048,
            memory_provider_id: prov.provider_id,
            memory_model: prov.model,
            memory_api_key_id: None,
        }
    }
}

impl RuntimeProfile {
    pub fn from_friend(friend: &Friend) -> crate::Result<Self> {
        let mut p = Self::default();

        match friend.backend_kind {
            BackendKind::Api => {
                let cfg: ApiBackendConfig =
                    serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
                apply_worker_bee_from_api(&mut p, friend, &cfg);
            }
            BackendKind::Assistant => {
                let ac: AssistantBackendConfig =
                    serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
                let pty = PtyBackendConfig {
                    preset: Some(WORKER_BEE_CLI_PRESET.into()),
                    cmd: "worker-bee".into(),
                    provider_id: ac.provider_id,
                    model: ac.model,
                    api_key_id: ac.api_key_id,
                    skills_dir: Some(ac.skills_dir),
                    memory_top_k: Some(ac.memory_top_k),
                    ..Default::default()
                };
                apply_worker_bee_from_pty(&mut p, friend, &pty);
            }
            BackendKind::Pty => {
                let mut cfg: PtyBackendConfig =
                    serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
                crate::friend_cli::normalize_pty_config(&mut cfg, friend.is_builtin);
                if is_external_cli_preset(&cfg) {
                    let preset = resolve_pty_preset(&cfg)?;
                    let cmd = if cfg.cmd.is_empty() {
                        None
                    } else {
                        Some(cfg.cmd.clone())
                    };
                    p.inference = InferenceBackend::ExternalCli(CliInferenceConfig {
                        preset,
                        cmd,
                    });
                } else if pty_preset_is_worker_bee(&cfg) {
                    apply_worker_bee_from_pty(&mut p, friend, &cfg);
                } else {
                    return Err(crate::Error::bad_request(
                        "好友未配置 CLI 预设，请在编辑里选择 Codex / Claude / Worker Bee 并保存",
                    ));
                }
            }
            BackendKind::Human => {}
        }

        p.workspace_cwd = resolve_workspace(friend, None)?;
        Ok(p)
    }

    pub fn workspace_for_context(
        &self,
        friend: &Friend,
        ctx: &crate::agent::ChatContext,
    ) -> crate::Result<Option<String>> {
        resolve_workspace(friend, Some(ctx))
    }

    pub fn provider_inference(&self) -> Option<&ProviderInferenceConfig> {
        match &self.inference {
            InferenceBackend::WorkerBee(w) => Some(&w.provider),
            _ => None,
        }
    }

    pub fn is_worker_bee(&self) -> bool {
        matches!(self.inference, InferenceBackend::WorkerBee(_))
    }
}

fn apply_worker_bee_from_api(p: &mut RuntimeProfile, friend: &Friend, cfg: &ApiBackendConfig) {
    p.inference = InferenceBackend::WorkerBee(WorkerBeeInferenceConfig {
        instance_id: friend.id.clone(),
        provider: resolve_worker_bee_provider(
            &cfg.provider_id,
            &cfg.model,
            cfg.api_key_id.clone(),
        )
        .with_model_chain(cfg.model_chain.clone()),
        skills_dir: p.skills_dir.clone(),
        memory_top_k: p.memory_top_k,
    });
    p.params = cfg.params.clone();
    if let Some(t) = cfg.params.temperature {
        p.temperature = t;
    }
    if let Some(m) = cfg.params.max_tokens {
        p.max_tokens = m;
    }
    sync_memory_from_worker_bee(p);
}

fn apply_worker_bee_from_pty(p: &mut RuntimeProfile, friend: &Friend, cfg: &PtyBackendConfig) {
    let skills = cfg
        .skills_dir
        .clone()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| p.skills_dir.clone());
    let mem_k = cfg.memory_top_k.unwrap_or(p.memory_top_k);
    p.inference = InferenceBackend::WorkerBee(WorkerBeeInferenceConfig {
        instance_id: friend.id.clone(),
        provider: resolve_worker_bee_provider(
            &cfg.provider_id,
            &cfg.model,
            cfg.api_key_id.clone(),
        )
        .with_model_chain(cfg.model_chain.clone()),
        skills_dir: skills.clone(),
        memory_top_k: mem_k,
    });
    p.skills_dir = skills;
    p.memory_top_k = mem_k;
    p.params = cfg.params.clone();
    sync_memory_from_worker_bee(p);
}

fn sync_memory_from_worker_bee(p: &mut RuntimeProfile) {
    if let InferenceBackend::WorkerBee(w) = &p.inference {
        p.memory_provider_id = w.provider.provider_id.clone();
        p.memory_model = w.provider.model.clone();
        p.memory_api_key_id = w.provider.api_key_id.clone();
    }
}

fn resolve_workspace(friend: &Friend, ctx: Option<&crate::agent::ChatContext>) -> crate::Result<Option<String>> {
    let cfg: PtyBackendConfig =
        serde_json::from_value(friend.backend_config.clone()).unwrap_or_default();
    if let Some(ctx) = ctx {
        if ctx.group_id.is_some() {
            return Ok(Some(crate::friend_cli::resolve_cli_workspace(
                &cfg,
                &friend.id,
                ctx.group_id.as_deref(),
                ctx.group_cli_workspace(),
            )?));
        }
    }
    if let Some(ref cwd) = cfg.cwd {
        let t = cwd.trim();
        if !t.is_empty() {
            return Ok(Some(cli_workspace::ensure_at(t)?));
        }
    }
    if let Ok(global) = std::env::var("HONEYCOMB_CLI_CWD") {
        let t = global.trim();
        if !t.is_empty() {
            return Ok(Some(cli_workspace::ensure_at(t)?));
        }
    }
    if friend.backend_kind != BackendKind::Human {
        return Ok(Some(cli_workspace::ensure_for_friend(&friend.id)?));
    }
    Ok(None)
}

/// 可选：在 `backend_config` 里显式写 runtime 段覆盖默认行为。
#[derive(Debug, Clone, Deserialize, Default)]
pub struct RuntimeConfigOverlay {
    #[serde(default)]
    pub memory_top_k: Option<usize>,
    #[serde(default)]
    pub skills_dir: Option<String>,
    #[serde(default)]
    pub mcp_servers: Option<Vec<String>>,
    #[serde(default)]
    pub max_tool_rounds: Option<usize>,
    #[serde(default)]
    pub workspace_cwd: Option<String>,
}
