use std::sync::Arc;

use serde::Deserialize;

use super::config::EvolutionLoopConfig;
use super::optimization::{OptimizationItem, OptimizationReport, OptimizationSeverity};
use crate::judge::JudgeService;
use crate::provider::ProviderRegistry;
use crate::{Error, Result};

const ANALYZE_SYSTEM: &str =
    "你是源码质量分析助手。根据静态扫描摘要，输出可执行的优化项列表。只输出 JSON。";

#[derive(Debug, Deserialize)]
struct LlmItemsRaw {
    #[serde(default)]
    items: Vec<LlmItemRaw>,
}

#[derive(Debug, Deserialize)]
struct LlmItemRaw {
    title: String,
    #[serde(default)]
    severity: Option<String>,
    #[serde(default)]
    related_paths: Vec<String>,
    #[serde(default)]
    summary: Option<String>,
    #[serde(default)]
    suggestion: Option<String>,
}

pub async fn enhance_report_with_llm(
    providers: &Arc<ProviderRegistry>,
    judge: &Arc<JudgeService>,
    evo: &EvolutionLoopConfig,
    report: &mut OptimizationReport,
) -> Result<()> {
    if !evo.analyze_use_llm || report.items.is_empty() {
        return Ok(());
    }

    let summary: String = report
        .items
        .iter()
        .take(15)
        .map(|i| format!("- [{}] {}: {}", severity_str(&i.severity), i.title, i.summary))
        .collect::<Vec<_>>()
        .join("\n");

    let prompt = format!(
        "工作区已扫描 {} 个文件。静态发现：\n{summary}\n\n\
        请补充 0～5 条**高价值**优化项（不要重复上文），输出 JSON：\n\
        {{\"items\":[{{\"title\":\"\",\"severity\":\"high|medium|low\",\"related_paths\":[],\"summary\":\"\",\"suggestion\":\"\"}}]}}",
        report.scanned_files
    );

    let raw = complete_evolution_json(providers, judge, evo, ANALYZE_SYSTEM, &prompt).await?;
    let parsed: LlmItemsRaw = parse_json(&raw)?;
    for (idx, item) in parsed.items.into_iter().enumerate().take(5) {
        if report.items.iter().any(|x| title_near(&x.title, &item.title)) {
            continue;
        }
        report.items.push(OptimizationItem {
            id: format!("opt-llm-{idx}"),
            title: item.title,
            severity: parse_severity(item.severity.as_deref()),
            related_paths: item.related_paths,
            summary: item.summary.unwrap_or_default(),
            suggestion: item.suggestion.unwrap_or_default(),
            source: "llm".into(),
        });
    }
    report.llm_enhanced = true;
    Ok(())
}

async fn complete_evolution_json(
    providers: &Arc<ProviderRegistry>,
    judge: &Arc<JudgeService>,
    evo: &EvolutionLoopConfig,
    system: &str,
    user_prompt: &str,
) -> Result<String> {
    use seven_chat_agent_judge::{LlmJudgeInput, LlmJudgePort};
    use crate::judge::ProviderLlmJudgePort;

    let group = synthetic_group_for_evolution(evo);
    let target = judge
        .resolve_judge_llm_target(&group)
        .map_err(|e| Error::Config(e))?;
    let port = ProviderLlmJudgePort::new(providers.clone());
    let raw = port
        .complete_json(LlmJudgeInput {
            provider_id: target.provider_id,
            model: target.model,
            api_key_id: target.api_key_id,
            system: system.into(),
            user_prompt: user_prompt.into(),
            max_tokens: Some(1024),
        })
        .await
        .map_err(|e| Error::Config(e))?;
    Ok(raw)
}

fn synthetic_group_for_evolution(evo: &EvolutionLoopConfig) -> crate::domain::GroupSettings {
    let mut g = crate::domain::GroupSettings::default();
    if let Some(ref pid) = evo.judge_provider_id {
        g.judge.llm.provider_id = Some(pid.clone());
    }
    if let Some(ref m) = evo.judge_model {
        g.judge.llm.model = Some(m.clone());
    }
    g
}

fn parse_json(raw: &str) -> Result<LlmItemsRaw> {
    let start = raw.find('{').ok_or_else(|| Error::Config("LLM JSON 无对象".into()))?;
    let end = raw.rfind('}').ok_or_else(|| Error::Config("LLM JSON 无对象".into()))?;
    serde_json::from_str(&raw[start..=end]).map_err(|e| Error::Config(format!("LLM parse: {e}")))
}

fn parse_severity(s: Option<&str>) -> OptimizationSeverity {
    match s.map(|x| x.to_lowercase()).as_deref() {
        Some("high") => OptimizationSeverity::High,
        Some("low") => OptimizationSeverity::Low,
        _ => OptimizationSeverity::Medium,
    }
}

fn severity_str(s: &OptimizationSeverity) -> &'static str {
    match s {
        OptimizationSeverity::High => "high",
        OptimizationSeverity::Medium => "medium",
        OptimizationSeverity::Low => "low",
    }
}

fn title_near(a: &str, b: &str) -> bool {
    seven_chat_agent_judge::text_similarity(a, b) >= 0.55
}
