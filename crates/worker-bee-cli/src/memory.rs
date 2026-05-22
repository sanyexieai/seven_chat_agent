use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Default, Serialize, Deserialize)]
pub struct MemoryStore {
    pub entries: Vec<MemoryEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEntry {
    pub ts: String,
    pub summary: String,
}

pub struct Memory {
    path: PathBuf,
    store: MemoryStore,
}

impl Memory {
    pub fn open(data_dir: &Path) -> Result<Self> {
        std::fs::create_dir_all(data_dir)?;
        let path = data_dir.join("memories.json");
        let store = if path.exists() {
            let raw = std::fs::read_to_string(&path)?;
            serde_json::from_str(&raw).unwrap_or_default()
        } else {
            MemoryStore::default()
        };
        Ok(Self { path, store })
    }

    pub fn recall_top(&self, k: usize) -> Vec<&MemoryEntry> {
        self.store.entries.iter().rev().take(k).collect()
    }

    pub fn append(&mut self, summary: impl Into<String>) -> Result<()> {
        self.store.entries.push(MemoryEntry {
            ts: chrono_lite_now(),
            summary: summary.into(),
        });
        self.persist()
    }

    fn persist(&self) -> Result<()> {
        let raw = serde_json::to_string_pretty(&self.store)?;
        std::fs::write(&self.path, raw).with_context(|| format!("write {}", self.path.display()))
    }
}

fn chrono_lite_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    secs.to_string()
}

pub fn format_recall_block(entries: &[&MemoryEntry]) -> String {
    if entries.is_empty() {
        return String::new();
    }
    let mut s = String::from("\n\n[工蜂记忆]\n");
    for e in entries {
        s.push_str("- ");
        s.push_str(&e.summary);
        s.push('\n');
    }
    s
}
