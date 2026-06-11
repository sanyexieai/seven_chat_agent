use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EvolutionRunKind {
    SyncSource,
    BuildCli,
    PipelineSyncBuild,
    AnalyzeSource,
    SyncIssues,
    PipelineAnalyzeIssues,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EvolutionRunStatus {
    Running,
    Succeeded,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvolutionRunLog {
    pub id: String,
    pub kind: EvolutionRunKind,
    pub status: EvolutionRunStatus,
    pub started_at: DateTime<Utc>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub finished_at: Option<DateTime<Utc>>,
    #[serde(default)]
    pub steps: Vec<EvolutionStepLog>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub commit: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub backup_dir: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub built_binary: Option<String>,
    /// 关联的分析/同步报告文件（相对 evolution/runs/）。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub artifact: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvolutionStepLog {
    pub name: String,
    pub ok: bool,
    #[serde(default)]
    pub detail: String,
    #[serde(default)]
    pub stdout: String,
    #[serde(default)]
    pub stderr: String,
}

impl EvolutionRunLog {
    pub fn new(id: String, kind: EvolutionRunKind) -> Self {
        Self {
            id,
            kind,
            status: EvolutionRunStatus::Running,
            started_at: Utc::now(),
            finished_at: None,
            steps: Vec::new(),
            error: None,
            commit: None,
            backup_dir: None,
            built_binary: None,
            artifact: None,
        }
    }

    pub fn push_step(&mut self, step: EvolutionStepLog) {
        self.steps.push(step);
    }

    pub fn finish_ok(&mut self) {
        self.status = EvolutionRunStatus::Succeeded;
        self.finished_at = Some(Utc::now());
    }

    pub fn finish_err(&mut self, msg: impl Into<String>) {
        self.status = EvolutionRunStatus::Failed;
        self.finished_at = Some(Utc::now());
        self.error = Some(msg.into());
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvolutionRunSummary {
    pub id: String,
    pub kind: EvolutionRunKind,
    pub status: EvolutionRunStatus,
    pub started_at: DateTime<Utc>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub finished_at: Option<DateTime<Utc>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}
