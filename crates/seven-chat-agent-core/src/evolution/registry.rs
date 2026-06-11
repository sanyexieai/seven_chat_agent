use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum LocalIssueStatus {
    Open,
    Claimed,
    Fixed,
    Wontfix,
}

impl Default for LocalIssueStatus {
    fn default() -> Self {
        Self::Open
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LocalIssueRecord {
    pub local_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub remote_url: Option<String>,
    pub first_seen_at: DateTime<Utc>,
    #[serde(default)]
    pub relevance_notes: String,
    #[serde(default)]
    pub relevance_boost: f32,
    #[serde(default)]
    pub status: LocalIssueStatus,
    #[serde(default)]
    pub related_paths: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub claimed_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CapabilityProfile {
    #[serde(default)]
    pub closed_labels: Vec<String>,
    #[serde(default)]
    pub avg_tokens_per_fix: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct EvolutionRegistry {
    #[serde(default)]
    pub issues: Vec<LocalIssueRecord>,
    #[serde(default)]
    pub capability: CapabilityProfile,
}

impl EvolutionRegistry {
    pub fn upsert_issue(&mut self, record: LocalIssueRecord) {
        if let Some(i) = self.issues.iter().position(|x| x.local_id == record.local_id) {
            self.issues[i] = record;
        } else {
            self.issues.push(record);
        }
    }
}
