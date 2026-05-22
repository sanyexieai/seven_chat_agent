use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CoreConfig {
    pub database_url: String,
    pub data_dir: String,
}

impl Default for CoreConfig {
    fn default() -> Self {
        Self {
            database_url: "sqlite://data/honeycomb.db".into(),
            data_dir: "data".into(),
        }
    }
}

impl CoreConfig {
    pub fn from_env() -> Self {
        let database_url = std::env::var("HONEYCOMB_DB")
            .unwrap_or_else(|_| "sqlite://data/honeycomb.db".into());
        let data_dir = std::env::var("HONEYCOMB_DATA").unwrap_or_else(|_| "data".into());
        Self {
            database_url,
            data_dir,
        }
    }
}
