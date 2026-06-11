use std::path::{Path, PathBuf};

use crate::{Error, Result};

pub struct EvolutionLayout {
    pub root: PathBuf,
}

impl EvolutionLayout {
    pub fn from_data_dir(data_dir: &str) -> Self {
        Self {
            root: PathBuf::from(data_dir).join("evolution"),
        }
    }

    pub fn ensure_dirs(&self) -> Result<()> {
        for sub in [
            "",
            "cli-backup",
            "workspaces",
            "runs",
        ] {
            let p = if sub.is_empty() {
                self.root.clone()
            } else {
                self.root.join(sub)
            };
            std::fs::create_dir_all(&p).map_err(|e| Error::Config(format!("mkdir {}: {e}", p.display())))?;
        }
        Ok(())
    }

    pub fn settings_path(&self) -> PathBuf {
        self.root.join("settings.json")
    }

    pub fn registry_path(&self) -> PathBuf {
        self.root.join("registry.json")
    }

    pub fn runs_dir(&self) -> PathBuf {
        self.root.join("runs")
    }

    pub fn cli_backup_dir(&self) -> PathBuf {
        self.root.join("cli-backup")
    }

    pub fn workspace_path(&self, workspace_dir: &str) -> PathBuf {
        self.root.join("workspaces").join(workspace_dir)
    }

    pub fn run_log_path(&self, run_id: &str) -> PathBuf {
        self.runs_dir().join(format!("{run_id}.json"))
    }

    pub fn resolve_under_workspaces(&self, workspace_dir: &str) -> Result<PathBuf> {
        let base = self.root.join("workspaces").canonicalize().map_err(|e| {
            Error::Config(format!("workspaces dir: {e}"))
        })?;
        let target = self.workspace_path(workspace_dir);
        let joined = if target.exists() {
            target.canonicalize().map_err(|e| Error::Config(e.to_string()))?
        } else {
            target.clone()
        };
        if joined.starts_with(&base) || !target.exists() {
            Ok(target)
        } else {
            Err(Error::bad_request("工作区路径越界"))
        }
    }
}

pub fn repo_slug_from_url(url: &str) -> String {
    let t = url.trim().trim_end_matches(".git");
    t.rsplit('/')
        .take(2)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect::<Vec<_>>()
        .join("-")
        .replace(':', "-")
}

pub fn workspace_dir_name(source_id: &str, custom: &str) -> String {
    if !custom.trim().is_empty() {
        return custom.trim().to_string();
    }
    source_id.trim().to_string()
}

pub fn path_exists(p: &Path) -> bool {
    p.exists()
}
