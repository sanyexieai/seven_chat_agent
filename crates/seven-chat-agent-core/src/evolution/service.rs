use std::sync::Arc;

use super::analyze::analyze_workspace;
use super::cli_build::build_cli;
use super::config::EvolutionSettings;
use super::git_sync::sync_source;
use super::issue_sync::sync_issues_for_items;
use super::layout::workspace_dir_name;
use super::llm_analyze::enhance_report_with_llm;
use super::optimization::{IssueSyncReport, OptimizationReport};
use super::registry::EvolutionRegistry;
use super::run_log::{EvolutionRunKind, EvolutionRunLog, EvolutionRunStatus};
use super::store::EvolutionStore;
use crate::judge::JudgeService;
use crate::provider::ProviderRegistry;
use crate::store::SqliteStore;
use crate::{Error, Result};

pub struct EvolutionService {
    store: Arc<EvolutionStore>,
    sqlite: Arc<SqliteStore>,
    providers: Arc<ProviderRegistry>,
    judge: Arc<JudgeService>,
}

impl EvolutionService {
    pub fn new(
        data_dir: &str,
        sqlite: Arc<SqliteStore>,
        providers: Arc<ProviderRegistry>,
        judge: Arc<JudgeService>,
    ) -> Result<Self> {
        Ok(Self {
            store: Arc::new(EvolutionStore::new(data_dir)?),
            sqlite,
            providers,
            judge,
        })
    }

    pub fn evolution_store(&self) -> &EvolutionStore {
        &self.store
    }

    pub fn load_settings(&self) -> Result<EvolutionSettings> {
        self.store.load_settings()
    }

    pub fn save_settings(&self, settings: &EvolutionSettings) -> Result<EvolutionSettings> {
        self.store.save_settings(settings)?;
        Ok(settings.clone())
    }

    pub fn load_registry(&self) -> Result<EvolutionRegistry> {
        self.store.load_registry()
    }

    pub fn save_registry(&self, registry: &EvolutionRegistry) -> Result<EvolutionRegistry> {
        self.store.save_registry(registry)?;
        Ok(registry.clone())
    }

    async fn ensure_evolution_budget(&self) -> Result<()> {
        let global = self.sqlite.get_assistant_global_settings().await?;
        if global.evolution_enabled && !self.sqlite.evolution_budget_available(&global) {
            return Err(Error::bad_request("进化 token 池已用尽"));
        }
        Ok(())
    }

    async fn record_evolution_tokens(&self, est: u64) {
        if est > 0 {
            let _ = self.sqlite.consume_evolution_tokens(est).await;
        }
    }

    fn require_source(settings: &EvolutionSettings) -> Result<&super::config::SourceCenterConfig> {
        settings
            .source
            .as_ref()
            .filter(|s| !s.remote_url.trim().is_empty())
            .ok_or_else(|| Error::bad_request("请配置 source.remote_url 并启用 source 模式"))
    }

    pub async fn run_sync_source(&self) -> Result<EvolutionRunLog> {
        let settings = self.load_settings()?;
        let source = Self::require_source(&settings)?;
        let id = EvolutionStore::new_run_id();
        let mut run = EvolutionRunLog::new(id, EvolutionRunKind::SyncSource);
        self.store.save_run(&run)?;

        let result = sync_source(self.store.layout(), source).await;
        match result {
            Ok(r) => {
                run.push_step(r.step);
                run.commit = r.commit;
                if run.steps.last().is_some_and(|s| s.ok) {
                    run.finish_ok();
                } else {
                    run.finish_err("git 同步失败");
                }
            }
            Err(e) => {
                run.push_step(super::run_log::EvolutionStepLog {
                    name: "git_sync".into(),
                    ok: false,
                    detail: e.to_string(),
                    stdout: String::new(),
                    stderr: String::new(),
                });
                run.finish_err(e.to_string());
            }
        }
        self.store.save_run(&run)?;
        Ok(run)
    }

    pub async fn run_build_cli(&self) -> Result<EvolutionRunLog> {
        let mut settings = self.load_settings()?;
        let source = Self::require_source(&settings)?.clone();
        let ws_name = workspace_dir_name(&source.id, &source.workspace_dir);
        let id = EvolutionStore::new_run_id();
        let mut run = EvolutionRunLog::new(id, EvolutionRunKind::BuildCli);
        self.store.save_run(&run)?;

        let result = build_cli(
            self.store.layout(),
            &settings.cli,
            &source,
            &ws_name,
        )
        .await;
        match result {
            Ok(r) => {
                for step in r.steps {
                    run.push_step(step);
                }
                if let Some(dir) = r.backup_dir {
                    run.backup_dir = Some(dir.display().to_string());
                }
                if let Some(bin) = r.built_binary {
                    let path = bin.display().to_string();
                    run.built_binary = Some(path.clone());
                    settings.cli.active_candidate_path = Some(path);
                    let _ = self.store.save_settings(&settings);
                }
                if r.health_ok {
                    run.finish_ok();
                } else {
                    run.finish_err("编译或健康检查未通过");
                }
            }
            Err(e) => run.finish_err(e.to_string()),
        }
        self.store.save_run(&run)?;
        Ok(run)
    }

    pub async fn run_pipeline_sync_build(&self) -> Result<EvolutionRunLog> {
        let id = EvolutionStore::new_run_id();
        let mut run = EvolutionRunLog::new(id.clone(), EvolutionRunKind::PipelineSyncBuild);
        self.store.save_run(&run)?;

        let sync = self.run_sync_source().await?;
        for step in &sync.steps {
            run.push_step(step.clone());
        }
        run.commit = sync.commit;
        if sync.status != EvolutionRunStatus::Succeeded {
            run.finish_err(sync.error.unwrap_or_else(|| "sync-source 失败".into()));
            self.store.save_run(&run)?;
            return Ok(run);
        }

        let build = self.run_build_cli().await?;
        for step in &build.steps {
            run.push_step(step.clone());
        }
        run.backup_dir = build.backup_dir;
        run.built_binary = build.built_binary;
        if build.status == EvolutionRunStatus::Succeeded {
            run.finish_ok();
        } else {
            run.finish_err(build.error.unwrap_or_else(|| "build-cli 失败".into()));
        }
        self.store.save_run(&run)?;
        Ok(run)
    }

    pub async fn run_analyze_source(&self) -> Result<(EvolutionRunLog, OptimizationReport)> {
        self.ensure_evolution_budget().await?;
        let settings = self.load_settings()?;
        if !settings.evolution.enabled {
            return Err(Error::bad_request("请先在配置中启用 evolution.enabled"));
        }
        let source = Self::require_source(&settings)?.clone();
        let ws_name = workspace_dir_name(&source.id, &source.workspace_dir);

        let id = EvolutionStore::new_run_id();
        let mut run = EvolutionRunLog::new(id.clone(), EvolutionRunKind::AnalyzeSource);
        self.store.save_run(&run)?;

        let mut report = analyze_workspace(
            self.store.layout(),
            &source,
            &ws_name,
            None,
        )?;

        run.push_step(super::run_log::EvolutionStepLog {
            name: "static_analyze".into(),
            ok: true,
            detail: format!("发现 {} 条可优化项", report.items.len()),
            stdout: String::new(),
            stderr: String::new(),
        });

        if settings.evolution.analyze_use_llm {
            match enhance_report_with_llm(
                &self.providers,
                &self.judge,
                &settings.evolution,
                &mut report,
            )
            .await
            {
                Ok(()) => {
                    run.push_step(super::run_log::EvolutionStepLog {
                        name: "llm_enhance".into(),
                        ok: true,
                        detail: "LLM 已补充优化项".into(),
                        stdout: String::new(),
                        stderr: String::new(),
                    });
                    self.record_evolution_tokens(800).await;
                }
                Err(e) => {
                    run.push_step(super::run_log::EvolutionStepLog {
                        name: "llm_enhance".into(),
                        ok: false,
                        detail: e.to_string(),
                        stdout: String::new(),
                        stderr: String::new(),
                    });
                }
            }
        }

        let artifact = self.store.save_artifact(&id, "analyze", &report)?;
        run.artifact = Some(artifact);
        run.finish_ok();
        self.store.save_run(&run)?;
        Ok((run, report))
    }

    pub async fn run_sync_issues(
        &self,
        report: Option<OptimizationReport>,
    ) -> Result<(EvolutionRunLog, IssueSyncReport)> {
        self.ensure_evolution_budget().await?;
        let settings = self.load_settings()?;
        let report = match report {
            Some(r) => r,
            None => {
                let (_, r) = self.run_analyze_source().await?;
                r
            }
        };

        let id = EvolutionStore::new_run_id();
        let mut run = EvolutionRunLog::new(id.clone(), EvolutionRunKind::SyncIssues);
        self.store.save_run(&run)?;

        let mut registry = self.load_registry()?;
        let sync_report = sync_issues_for_items(
            &settings,
            &mut registry,
            &report.items,
            settings.evolution.max_issue_sync_items,
        )
        .await?;

        self.save_registry(&registry)?;

        let created = sync_report
            .results
            .iter()
            .filter(|r| matches!(r.action, super::optimization::IssueSyncAction::CreatedRemote))
            .count();
        let linked = sync_report
            .results
            .iter()
            .filter(|r| {
                matches!(
                    r.action,
                    super::optimization::IssueSyncAction::LinkedExisting
                )
            })
            .count();
        let pending = sync_report
            .results
            .iter()
            .filter(|r| {
                matches!(
                    r.action,
                    super::optimization::IssueSyncAction::PendingApproval
                )
            })
            .count();

        run.push_step(super::run_log::EvolutionStepLog {
            name: "issue_sync".into(),
            ok: true,
            detail: format!(
                "处理 {} 条：关联 {linked}、新建 {created}、待审批 {pending}",
                sync_report.items_processed
            ),
            stdout: String::new(),
            stderr: String::new(),
        });

        let artifact = self.store.save_artifact(&id, "issues", &sync_report)?;
        run.artifact = Some(artifact);
        run.finish_ok();
        self.store.save_run(&run)?;
        self.record_evolution_tokens(400).await;
        Ok((run, sync_report))
    }

    pub async fn run_pipeline_analyze_issues(
        &self,
    ) -> Result<(EvolutionRunLog, OptimizationReport, IssueSyncReport)> {
        let id = EvolutionStore::new_run_id();
        let mut run = EvolutionRunLog::new(id.clone(), EvolutionRunKind::PipelineAnalyzeIssues);
        self.store.save_run(&run)?;

        let (analyze_run, report) = self.run_analyze_source().await?;
        for step in &analyze_run.steps {
            run.push_step(step.clone());
        }
        if analyze_run.status != EvolutionRunStatus::Succeeded {
            run.finish_err(analyze_run.error.unwrap_or_else(|| "分析失败".into()));
            self.store.save_run(&run)?;
            return Err(Error::Config(
                run.error.clone().unwrap_or_else(|| "分析失败".into()),
            ));
        }

        let (sync_run, issue_report) = self.run_sync_issues(Some(report.clone())).await?;
        for step in &sync_run.steps {
            run.push_step(step.clone());
        }
        if sync_run.status != EvolutionRunStatus::Succeeded {
            run.finish_err(sync_run.error.unwrap_or_else(|| "issue 同步失败".into()));
            self.store.save_run(&run)?;
            return Err(Error::Config(
                run.error.clone().unwrap_or_else(|| "issue 同步失败".into()),
            ));
        }

        let _ = self
            .store
            .save_artifact(&id, "analyze", &report)?;
        let artifact = self
            .store
            .save_artifact(&id, "issues", &issue_report)?;
        run.artifact = Some(artifact);
        run.finish_ok();
        self.store.save_run(&run)?;
        Ok((run, report, issue_report))
    }

    pub fn get_run(&self, id: &str) -> Result<Option<EvolutionRunLog>> {
        self.store.load_run(id)
    }

    pub fn list_runs(&self, limit: usize) -> Result<Vec<super::run_log::EvolutionRunSummary>> {
        self.store.list_runs(limit)
    }

    pub fn load_report_artifact(&self, artifact: &str) -> Result<Option<OptimizationReport>> {
        self.store.load_artifact(artifact)
    }
}
