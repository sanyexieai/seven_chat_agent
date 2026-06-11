use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeMode {
    #[default]
    Cli,
    Source,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvolutionCliConfig {
    /// 当前生产使用的基础 CLI 路径。
    #[serde(default)]
    pub binary_path: String,
    #[serde(default)]
    pub preset: String,
    /// 健康检查通过后可选的候选 CLI（不自动覆盖 binary_path）。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub active_candidate_path: Option<String>,
}

impl Default for EvolutionCliConfig {
    fn default() -> Self {
        Self {
            binary_path: String::new(),
            preset: "worker-bee".into(),
            active_candidate_path: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceCenterConfig {
    pub id: String,
    pub remote_url: String,
    #[serde(default = "default_branch")]
    pub branch: String,
    /// 相对 `evolution/workspaces/` 的目录名；空则用 `id`。
    #[serde(default)]
    pub workspace_dir: String,
    #[serde(default)]
    pub build_command: String,
    #[serde(default)]
    pub test_command: String,
    /// 相对工作区根目录的产物路径。
    #[serde(default)]
    pub built_binary_path: String,
    #[serde(default)]
    pub shallow_depth: u32,
}

fn default_branch() -> String {
    "main".into()
}

impl Default for SourceCenterConfig {
    fn default() -> Self {
        Self {
            id: "seven-chat-agent".into(),
            remote_url: String::new(),
            branch: default_branch(),
            workspace_dir: String::new(),
            build_command: "cargo build --release -p seven-chat-agent-cli".into(),
            test_command: "cargo test --workspace --no-run".into(),
            built_binary_path: "target/release/seven-chat-agent-cli".into(),
            shallow_depth: 1,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvolutionLoopConfig {
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default = "default_max_concurrent")]
    pub max_concurrent_tasks: u32,
    #[serde(default = "default_true")]
    pub require_approval_before_push: bool,
    #[serde(default)]
    pub git_platform: String,
    #[serde(default)]
    pub trusted_orgs: Vec<String>,
    /// 环境变量名，用于读取 GitHub Token（默认 GITHUB_TOKEN）。
    #[serde(default = "default_github_token_env")]
    pub github_token_env: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub github_token: Option<String>,
    #[serde(default = "default_issue_similarity")]
    pub issue_similarity_threshold: f32,
    #[serde(default = "default_true")]
    pub require_approval_before_create_issue: bool,
    #[serde(default)]
    pub default_issue_labels: Vec<String>,
    #[serde(default = "default_true")]
    pub analyze_use_llm: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub judge_provider_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub judge_model: Option<String>,
    /// 单次 issue 同步最多处理条数。
    #[serde(default = "default_max_issue_sync_items")]
    pub max_issue_sync_items: u32,
}

fn default_github_token_env() -> String {
    "GITHUB_TOKEN".into()
}

fn default_issue_similarity() -> f32 {
    0.65
}

fn default_max_issue_sync_items() -> u32 {
    8
}

fn default_true() -> bool {
    true
}

fn default_max_concurrent() -> u32 {
    1
}

impl Default for EvolutionLoopConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            max_concurrent_tasks: default_max_concurrent(),
            require_approval_before_push: true,
            git_platform: "github".into(),
            trusted_orgs: Vec::new(),
            github_token_env: default_github_token_env(),
            github_token: None,
            issue_similarity_threshold: default_issue_similarity(),
            require_approval_before_create_issue: true,
            default_issue_labels: vec!["enhancement".into()],
            analyze_use_llm: true,
            judge_provider_id: None,
            judge_model: None,
            max_issue_sync_items: default_max_issue_sync_items(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvolutionSettings {
    #[serde(default)]
    pub runtime_mode: RuntimeMode,
    #[serde(default)]
    pub cli: EvolutionCliConfig,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<SourceCenterConfig>,
    #[serde(default)]
    pub evolution: EvolutionLoopConfig,
}

impl Default for EvolutionSettings {
    fn default() -> Self {
        Self {
            runtime_mode: RuntimeMode::Cli,
            cli: EvolutionCliConfig::default(),
            source: None,
            evolution: EvolutionLoopConfig::default(),
        }
    }
}

impl EvolutionSettings {
    pub fn source_enabled(&self) -> bool {
        self.runtime_mode == RuntimeMode::Source
            && self
                .source
                .as_ref()
                .is_some_and(|s| !s.remote_url.trim().is_empty())
    }
}
