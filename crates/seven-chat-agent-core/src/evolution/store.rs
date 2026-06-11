use std::fs;

use uuid::Uuid;

use super::config::EvolutionSettings;
use super::layout::EvolutionLayout;
use super::registry::EvolutionRegistry;
use super::run_log::{EvolutionRunLog, EvolutionRunSummary};
use crate::{Error, Result};

pub struct EvolutionStore {
    layout: EvolutionLayout,
}

impl EvolutionStore {
    pub fn new(data_dir: &str) -> Result<Self> {
        let layout = EvolutionLayout::from_data_dir(data_dir);
        layout.ensure_dirs()?;
        Ok(Self { layout })
    }

    pub fn layout(&self) -> &EvolutionLayout {
        &self.layout
    }

    pub fn load_settings(&self) -> Result<EvolutionSettings> {
        let path = self.layout.settings_path();
        if !path.exists() {
            let default = EvolutionSettings::default();
            self.save_settings(&default)?;
            return Ok(default);
        }
        let raw = fs::read_to_string(&path).map_err(|e| Error::Config(e.to_string()))?;
        serde_json::from_str(&raw).map_err(|e| Error::Config(format!("settings.json: {e}")))
    }

    pub fn save_settings(&self, settings: &EvolutionSettings) -> Result<()> {
        let path = self.layout.settings_path();
        let raw = serde_json::to_string_pretty(settings)?;
        fs::write(&path, raw).map_err(|e| Error::Config(e.to_string()))
    }

    pub fn load_registry(&self) -> Result<EvolutionRegistry> {
        let path = self.layout.registry_path();
        if !path.exists() {
            let reg = EvolutionRegistry::default();
            self.save_registry(&reg)?;
            return Ok(reg);
        }
        let raw = fs::read_to_string(&path).map_err(|e| Error::Config(e.to_string()))?;
        serde_json::from_str(&raw).map_err(|e| Error::Config(format!("registry.json: {e}")))
    }

    pub fn save_registry(&self, registry: &EvolutionRegistry) -> Result<()> {
        let path = self.layout.registry_path();
        let raw = serde_json::to_string_pretty(registry)?;
        fs::write(&path, raw).map_err(|e| Error::Config(e.to_string()))
    }

    pub fn save_run(&self, run: &EvolutionRunLog) -> Result<()> {
        let path = self.layout.run_log_path(&run.id);
        let raw = serde_json::to_string_pretty(run)?;
        fs::write(&path, raw).map_err(|e| Error::Config(e.to_string()))
    }

    pub fn load_run(&self, id: &str) -> Result<Option<EvolutionRunLog>> {
        let path = self.layout.run_log_path(id);
        if !path.exists() {
            return Ok(None);
        }
        let raw = fs::read_to_string(&path).map_err(|e| Error::Config(e.to_string()))?;
        let run: EvolutionRunLog =
            serde_json::from_str(&raw).map_err(|e| Error::Config(format!("run log: {e}")))?;
        Ok(Some(run))
    }

    pub fn list_runs(&self, limit: usize) -> Result<Vec<EvolutionRunSummary>> {
        let dir = self.layout.runs_dir();
        let mut entries: Vec<_> = fs::read_dir(&dir)
            .map_err(|e| Error::Config(e.to_string()))?
            .filter_map(|e| e.ok())
            .filter(|e| e.path().extension().is_some_and(|x| x == "json"))
            .collect();
        entries.sort_by_key(|e| e.file_name());
        entries.reverse();
        let mut out = Vec::new();
        for ent in entries.into_iter().take(limit) {
            let raw = fs::read_to_string(ent.path()).map_err(|e| Error::Config(e.to_string()))?;
            if let Ok(run) = serde_json::from_str::<EvolutionRunLog>(&raw) {
                out.push(EvolutionRunSummary {
                    id: run.id,
                    kind: run.kind,
                    status: run.status,
                    started_at: run.started_at,
                    finished_at: run.finished_at,
                    error: run.error,
                });
            }
        }
        Ok(out)
    }

    pub fn new_run_id() -> String {
        format!("evo-{}", Uuid::new_v4())
    }

    pub fn save_artifact<T: serde::Serialize>(&self, run_id: &str, suffix: &str, value: &T) -> Result<String> {
        let name = format!("{run_id}-{suffix}.json");
        let path = self.layout.runs_dir().join(&name);
        let raw = serde_json::to_string_pretty(value)?;
        fs::write(&path, raw).map_err(|e| Error::Config(e.to_string()))?;
        Ok(name)
    }

    pub fn load_artifact<T: serde::de::DeserializeOwned>(
        &self,
        artifact_name: &str,
    ) -> Result<Option<T>> {
        let path = self.layout.runs_dir().join(artifact_name);
        if !path.exists() {
            return Ok(None);
        }
        let raw = fs::read_to_string(&path).map_err(|e| Error::Config(e.to_string()))?;
        serde_json::from_str(&raw)
            .map_err(|e| Error::Config(format!("artifact: {e}")))
            .map(Some)
    }
}
