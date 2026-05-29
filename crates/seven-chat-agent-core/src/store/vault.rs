use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use parking_lot::Mutex;

use crate::Result;

/// SecretVault stores API keys and other secrets.
///
/// Storage layout:
/// - `plain:<value>` returns the literal value (handy for tests).
/// - `env:<NAME>` reads an environment variable on every access.
/// - `keychain:<name>` goes through the OS keychain when the crate is built
///   with `--features keychain` (`keyring` crate); otherwise it falls back to
///   the JSON cache below.
/// - Anything else is stored in an on-disk JSON file (default
///   `./data/vault.json`, overridable via `SEVEN_CHAT_AGENT_VAULT`) with an
///   in-memory cache backing it.
#[derive(Clone)]
pub struct SecretVault {
    inner: Arc<Mutex<VaultInner>>,
}

struct VaultInner {
    path: PathBuf,
    cache: HashMap<String, String>,
}

impl SecretVault {
    pub fn new() -> Self {
        let path = std::env::var("SEVEN_CHAT_AGENT_VAULT")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("data/vault.json"));
        let cache = read_vault(&path).unwrap_or_default();
        Self {
            inner: Arc::new(Mutex::new(VaultInner { path, cache })),
        }
    }

    pub fn get(&self, secret_ref: &str) -> Option<String> {
        if let Some(rest) = secret_ref.strip_prefix("env:") {
            return std::env::var(rest).ok();
        }
        if let Some(rest) = secret_ref.strip_prefix("plain:") {
            return Some(rest.to_string());
        }
        if let Some(rest) = secret_ref.strip_prefix("keychain:") {
            if let Some(v) = keychain_get(rest) {
                return Some(v);
            }
        }
        let inner = self.inner.lock();
        inner.cache.get(secret_ref).cloned()
    }

    pub fn set(&self, secret_ref: &str, value: &str) -> Result<()> {
        if let Some(rest) = secret_ref.strip_prefix("keychain:") {
            if keychain_set(rest, value).is_ok() {
                return Ok(());
            }
        }
        let mut inner = self.inner.lock();
        inner.cache.insert(secret_ref.to_string(), value.to_string());
        write_vault(&inner.path, &inner.cache)?;
        Ok(())
    }

    pub fn delete(&self, secret_ref: &str) -> Result<()> {
        if let Some(rest) = secret_ref.strip_prefix("keychain:") {
            keychain_delete(rest).ok();
        }
        let mut inner = self.inner.lock();
        inner.cache.remove(secret_ref);
        write_vault(&inner.path, &inner.cache)?;
        Ok(())
    }
}

#[cfg(feature = "keychain")]
fn keychain_get(name: &str) -> Option<String> {
    let entry = keyring::Entry::new("seven-chat-agent", name).ok()?;
    entry.get_password().ok()
}

#[cfg(feature = "keychain")]
fn keychain_set(name: &str, value: &str) -> std::result::Result<(), String> {
    let entry = keyring::Entry::new("seven-chat-agent", name).map_err(|e| e.to_string())?;
    entry.set_password(value).map_err(|e| e.to_string())
}

#[cfg(feature = "keychain")]
fn keychain_delete(name: &str) -> std::result::Result<(), String> {
    let entry = keyring::Entry::new("seven-chat-agent", name).map_err(|e| e.to_string())?;
    entry.delete_credential().map_err(|e| e.to_string())
}

#[cfg(not(feature = "keychain"))]
fn keychain_get(_name: &str) -> Option<String> {
    None
}

#[cfg(not(feature = "keychain"))]
fn keychain_set(_name: &str, _value: &str) -> std::result::Result<(), String> {
    Err("keychain feature disabled".into())
}

#[cfg(not(feature = "keychain"))]
fn keychain_delete(_name: &str) -> std::result::Result<(), String> {
    Err("keychain feature disabled".into())
}

fn read_vault(path: &Path) -> Option<HashMap<String, String>> {
    let bytes = std::fs::read(path).ok()?;
    serde_json::from_slice(&bytes).ok()
}

fn write_vault(path: &Path, data: &HashMap<String, String>) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("json.tmp");
    let bytes = serde_json::to_vec_pretty(data)?;
    std::fs::write(&tmp, bytes)?;
    std::fs::rename(&tmp, path)?;
    Ok(())
}

impl Default for SecretVault {
    fn default() -> Self {
        Self::new()
    }
}
