use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::env;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CoreConfig {
    pub database_url: String,
    pub data_dir: String,
}

fn default_database_url() -> String {
    if let Some(url) = env::var("SEVEN_CHAT_AGENT_DB", "HONEYCOMB_DB") {
        return url;
    }
    let new_path = Path::new("data/seven_chat_agent.db");
    let old_path = Path::new("data/honeycomb.db");
    if old_path.exists() && !new_path.exists() {
        "sqlite://data/honeycomb.db".into()
    } else {
        "sqlite://data/seven_chat_agent.db".into()
    }
}

impl Default for CoreConfig {
    fn default() -> Self {
        Self {
            database_url: default_database_url(),
            data_dir: "data".into(),
        }
    }
}

impl CoreConfig {
    pub fn from_env() -> Self {
        let database_url = default_database_url();
        let data_dir =
            env::var_or("SEVEN_CHAT_AGENT_DATA", "HONEYCOMB_DATA", "data");
        Self {
            database_url,
            data_dir,
        }
    }
}
