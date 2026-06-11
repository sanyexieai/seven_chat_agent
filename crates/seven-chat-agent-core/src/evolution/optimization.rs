use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OptimizationSeverity {
    Low,
    Medium,
    High,
}

impl Default for OptimizationSeverity {
    fn default() -> Self {
        Self::Medium
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OptimizationItem {
    pub id: String,
    pub title: String,
    pub severity: OptimizationSeverity,
    #[serde(default)]
    pub related_paths: Vec<String>,
    #[serde(default)]
    pub summary: String,
    #[serde(default)]
    pub suggestion: String,
    #[serde(default)]
    pub source: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OptimizationReport {
    pub workspace_dir: String,
    pub commit: Option<String>,
    pub scanned_files: u32,
    #[serde(default)]
    pub items: Vec<OptimizationItem>,
    #[serde(default)]
    pub llm_enhanced: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IssueSyncAction {
    LinkedExisting,
    CreatedRemote,
    PendingApproval,
    Skipped,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IssueSyncResult {
    pub item_id: String,
    pub item_title: String,
    pub action: IssueSyncAction,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub remote_url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub local_id: Option<String>,
    #[serde(default)]
    pub detail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IssueSyncReport {
    pub items_processed: u32,
    #[serde(default)]
    pub results: Vec<IssueSyncResult>,
}
