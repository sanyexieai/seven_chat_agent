pub mod agent;
pub mod cli_workspace;
pub mod friend_cli;
pub mod runtime;
pub mod config;
pub mod dispatcher;
pub mod domain;
pub mod error;
pub mod judge;
pub mod provider;
pub mod scheduler;
pub mod store;

pub use error::{Error, Result};

use std::sync::Arc;

use crate::agent::AgentRegistry;
use crate::dispatcher::MessageDispatcher;
use crate::provider::ProviderRegistry;
use crate::store::SqliteStore;

#[derive(Clone)]
pub struct Honeycomb {
    pub store: Arc<SqliteStore>,
    pub providers: Arc<ProviderRegistry>,
    pub agents: Arc<AgentRegistry>,
    pub dispatcher: Arc<MessageDispatcher>,
}

impl Honeycomb {
    pub async fn boot(database_url: &str) -> Result<Self> {
        let store = Arc::new(SqliteStore::connect(database_url).await?);
        store.migrate().await?;
        store.migrate_legacy_assistant_friends().await?;
        store.migrate_fixup_pty_worker_bee_configs().await?;
        store.seed_builtins().await?;

        let providers = Arc::new(ProviderRegistry::new(store.clone()).await?);
        let agents = Arc::new(AgentRegistry::new(store.clone(), providers.clone()));
        let dispatcher = Arc::new(MessageDispatcher::new(
            store.clone(),
            agents.clone(),
        ));

        Ok(Self {
            store,
            providers,
            agents,
            dispatcher,
        })
    }
}
