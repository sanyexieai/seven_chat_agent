//! 自我进化外环（E0～E2）：配置、注册表、源码同步、CLI 验证、分析与 Issue 同步。

mod analyze;
mod cli_build;
mod config;
mod git_sync;
mod github;
mod issue_sync;
mod layout;
mod llm_analyze;
mod optimization;
mod registry;
mod run_log;
mod service;
mod store;

pub use config::{
    EvolutionCliConfig, EvolutionLoopConfig, EvolutionSettings, RuntimeMode, SourceCenterConfig,
};
pub use registry::{
    CapabilityProfile, EvolutionRegistry, LocalIssueRecord, LocalIssueStatus,
};
pub use optimization::{
    IssueSyncAction, IssueSyncReport, IssueSyncResult, OptimizationItem, OptimizationReport,
    OptimizationSeverity,
};
pub use run_log::{
    EvolutionRunKind, EvolutionRunLog, EvolutionRunStatus, EvolutionRunSummary, EvolutionStepLog,
};
pub use service::EvolutionService;
pub use store::EvolutionStore;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn settings_roundtrip() {
        let dir = std::env::temp_dir().join(format!("evo-test-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&dir).unwrap();
        let store = EvolutionStore::new(dir.to_str().unwrap()).unwrap();
        let mut s = EvolutionSettings::default();
        s.runtime_mode = RuntimeMode::Source;
        s.source = Some(SourceCenterConfig {
            remote_url: "https://github.com/example/repo.git".into(),
            ..Default::default()
        });
        store.save_settings(&s).unwrap();
        let loaded = store.load_settings().unwrap();
        assert!(loaded.source_enabled());
    }

    #[test]
    fn registry_upsert() {
        let mut reg = EvolutionRegistry::default();
        reg.upsert_issue(LocalIssueRecord {
            local_id: "evo-1".into(),
            remote_url: None,
            first_seen_at: chrono::Utc::now(),
            relevance_notes: String::new(),
            relevance_boost: 0.0,
            status: LocalIssueStatus::Open,
            related_paths: vec![],
            claimed_at: None,
        });
        assert_eq!(reg.issues.len(), 1);
    }
}
