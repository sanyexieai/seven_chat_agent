use std::path::{Path, PathBuf};

use uuid::Uuid;

use super::config::SourceCenterConfig;
use super::layout::EvolutionLayout;
use super::optimization::{OptimizationItem, OptimizationReport, OptimizationSeverity};
use crate::{Error, Result};

const SKIP_DIRS: &[&str] = &[
    ".git",
    "target",
    "node_modules",
    "dist",
    ".cursor",
    "data",
];

const CODE_EXTENSIONS: &[&str] = &[".rs", ".ts", ".tsx", ".go", ".py"];

pub fn analyze_workspace(
    layout: &EvolutionLayout,
    _source: &SourceCenterConfig,
    workspace_dir: &str,
    commit: Option<String>,
) -> Result<OptimizationReport> {
    let ws = layout.workspace_path(workspace_dir);
    if !ws.exists() {
        return Err(Error::bad_request("工作区不存在，请先同步源码"));
    }

    let mut items = Vec::new();
    let mut scanned = 0u32;
    let mut large_files: Vec<(u32, PathBuf)> = Vec::new();
    let mut todo_hits = 0u32;
    let mut unwrap_hits = 0u32;

    for entry in walk_files(&ws)? {
        scanned += 1;
        let rel = entry
            .strip_prefix(&ws)
            .unwrap_or(&entry)
            .display()
            .to_string();
        if let Ok(content) = std::fs::read_to_string(&entry) {
            let lines = content.lines().count() as u32;
            if lines >= 800 {
                large_files.push((lines, entry.clone()));
            }
            if content.contains("TODO") || content.contains("FIXME") {
                todo_hits += 1;
                if items.len() < 12 {
                    items.push(OptimizationItem {
                        id: format!("opt-{}", Uuid::new_v4()),
                        title: format!("待办标记：{}", rel),
                        severity: OptimizationSeverity::Low,
                        related_paths: vec![rel.clone()],
                        summary: "文件含 TODO/FIXME".into(),
                        suggestion: "确认是否应转为 issue 或尽快处理".into(),
                        source: "static".into(),
                    });
                }
            }
            if entry.extension().is_some_and(|e| e == "rs") {
                let u = content.matches(".unwrap()").count()
                    + content.matches(".expect(").count();
                if u > 0 {
                    unwrap_hits += u as u32;
                    if u >= 5 && items.len() < 20 {
                        items.push(OptimizationItem {
                            id: format!("opt-{}", Uuid::new_v4()),
                            title: format!("过多 unwrap/expect：{}", rel),
                            severity: OptimizationSeverity::Medium,
                            related_paths: vec![rel],
                            summary: format!("约 {u} 处 unwrap/expect"),
                            suggestion: "改为可恢复错误或集中错误处理".into(),
                            source: "static".into(),
                        });
                    }
                }
            }
        }
    }

    large_files.sort_by(|a, b| b.0.cmp(&a.0));
    for (lines, path) in large_files.into_iter().take(5) {
        let rel = path.strip_prefix(&ws).unwrap_or(&path).display().to_string();
        items.push(OptimizationItem {
            id: format!("opt-{}", Uuid::new_v4()),
            title: format!("大文件需拆分：{}（{lines} 行）", rel),
            severity: OptimizationSeverity::Medium,
            related_paths: vec![rel],
            summary: format!("{lines} 行，维护成本高"),
            suggestion: "按模块职责拆分为更小单元".into(),
            source: "static".into(),
        });
    }

    if todo_hits > 12 {
        items.push(OptimizationItem {
            id: format!("opt-{}", Uuid::new_v4()),
            title: "全仓 TODO/FIXME 较多".into(),
            severity: OptimizationSeverity::Low,
            related_paths: vec![],
            summary: format!("约 {todo_hits} 个文件含待办标记"),
            suggestion: "批量梳理并关闭或建 issue 跟踪".into(),
            source: "static".into(),
        });
    }
    if unwrap_hits > 30 {
        items.push(OptimizationItem {
            id: format!("opt-{}", Uuid::new_v4()),
            title: "全仓 panic 风险点偏多".into(),
            severity: OptimizationSeverity::High,
            related_paths: vec![],
            summary: format!("累计约 {unwrap_hits} 处 unwrap/expect"),
            suggestion: "优先处理热路径与网络/IO 边界".into(),
            source: "static".into(),
        });
    }

    let docs = ws.join("docs");
    if docs.is_dir() {
        let md_count = walk_files(&docs)?.len();
        if md_count == 0 {
            items.push(OptimizationItem {
                id: format!("opt-{}", Uuid::new_v4()),
                title: "docs 目录为空".into(),
                severity: OptimizationSeverity::Low,
                related_paths: vec!["docs/".into()],
                summary: "缺少设计/运维文档".into(),
                suggestion: "补充架构与运维说明".into(),
                source: "static".into(),
            });
        }
    }

    Ok(OptimizationReport {
        workspace_dir: workspace_dir.to_string(),
        commit,
        scanned_files: scanned,
        items: dedupe_items(items),
        llm_enhanced: false,
    })
}

fn dedupe_items(items: Vec<OptimizationItem>) -> Vec<OptimizationItem> {
    let mut out = Vec::new();
    for item in items {
        if out.iter().any(|x: &OptimizationItem| x.title == item.title) {
            continue;
        }
        out.push(item);
    }
    out
}

fn walk_files(root: &Path) -> Result<Vec<PathBuf>> {
    let mut stack = vec![root.to_path_buf()];
    let mut files = Vec::new();
    while let Some(dir) = stack.pop() {
        let entries = std::fs::read_dir(&dir).map_err(|e| Error::Config(e.to_string()))?;
        for ent in entries.flatten() {
            let path = ent.path();
            let name = ent.file_name().to_string_lossy().to_string();
            if path.is_dir() {
                if SKIP_DIRS.contains(&name.as_str()) {
                    continue;
                }
                stack.push(path);
            } else if CODE_EXTENSIONS.iter().any(|ext| name.ends_with(ext)) {
                files.push(path);
            }
        }
    }
    Ok(files)
}
