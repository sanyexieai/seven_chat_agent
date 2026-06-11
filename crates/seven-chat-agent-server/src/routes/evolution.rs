use axum::extract::{Path, State};
use axum::routing::{get, post, put};
use axum::{Json, Router};
use seven_chat_agent_core::evolution::{
    EvolutionRegistry, EvolutionRunLog, EvolutionSettings, OptimizationReport,
};
use serde::Deserialize;

use crate::state::AppState;
use super::errors::ApiError;

pub fn evolution_router() -> Router<AppState> {
    Router::new()
        .route("/settings", get(get_settings).put(put_settings))
        .route("/registry", get(get_registry).put(put_registry))
        .route("/runs", get(list_runs))
        .route("/runs/:id", get(get_run))
        .route("/runs/sync-source", post(post_sync_source))
        .route("/runs/build-cli", post(post_build_cli))
        .route("/runs/pipeline-sync-build", post(post_pipeline))
        .route("/runs/analyze-source", post(post_analyze))
        .route("/runs/sync-issues", post(post_sync_issues))
        .route("/runs/pipeline-analyze-issues", post(post_pipeline_analyze))
}

async fn get_settings(State(s): State<AppState>) -> Result<Json<EvolutionSettings>, ApiError> {
    Ok(Json(s.core.evolution.load_settings()?))
}

async fn put_settings(
    State(s): State<AppState>,
    Json(body): Json<EvolutionSettings>,
) -> Result<Json<EvolutionSettings>, ApiError> {
    Ok(Json(s.core.evolution.save_settings(&body)?))
}

async fn get_registry(State(s): State<AppState>) -> Result<Json<EvolutionRegistry>, ApiError> {
    Ok(Json(s.core.evolution.load_registry()?))
}

async fn put_registry(
    State(s): State<AppState>,
    Json(body): Json<EvolutionRegistry>,
) -> Result<Json<EvolutionRegistry>, ApiError> {
    Ok(Json(s.core.evolution.save_registry(&body)?))
}

#[derive(Deserialize)]
struct ListRunsQuery {
    #[serde(default = "default_limit")]
    limit: usize,
}

fn default_limit() -> usize {
    30
}

async fn list_runs(
    State(s): State<AppState>,
    axum::extract::Query(q): axum::extract::Query<ListRunsQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let runs = s.core.evolution.list_runs(q.limit)?;
    Ok(Json(serde_json::json!({ "runs": runs })))
}

async fn get_run(
    State(s): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<EvolutionRunLog>, ApiError> {
    let run = s
        .core
        .evolution
        .get_run(&id)?
        .ok_or(ApiError::NotFound)?;
    Ok(Json(run))
}

async fn post_sync_source(State(s): State<AppState>) -> Result<Json<EvolutionRunLog>, ApiError> {
    Ok(Json(s.core.evolution.run_sync_source().await?))
}

async fn post_build_cli(State(s): State<AppState>) -> Result<Json<EvolutionRunLog>, ApiError> {
    Ok(Json(s.core.evolution.run_build_cli().await?))
}

async fn post_pipeline(State(s): State<AppState>) -> Result<Json<EvolutionRunLog>, ApiError> {
    Ok(Json(s.core.evolution.run_pipeline_sync_build().await?))
}

async fn post_analyze(
    State(s): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let (run, report) = s.core.evolution.run_analyze_source().await?;
    Ok(Json(serde_json::json!({ "run": run, "report": report })))
}

#[derive(Deserialize)]
struct SyncIssuesBody {
    #[serde(default)]
    report: Option<OptimizationReport>,
}

async fn post_sync_issues(
    State(s): State<AppState>,
    body: Option<Json<SyncIssuesBody>>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let report = match body {
        Some(Json(b)) => b.report,
        None => None,
    };
    let (run, sync) = s.core.evolution.run_sync_issues(report).await?;
    Ok(Json(serde_json::json!({ "run": run, "sync": sync })))
}

async fn post_pipeline_analyze(
    State(s): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let (run, report, sync) = s.core.evolution.run_pipeline_analyze_issues().await?;
    Ok(Json(serde_json::json!({ "run": run, "report": report, "sync": sync })))
}
