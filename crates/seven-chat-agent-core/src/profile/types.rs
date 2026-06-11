use serde::{Deserialize, Serialize};
use seven_chat_agent_judge::{CoordinationLevel, InitiativeLevel, RoutingHints};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct MemberProfile {
    #[serde(default = "default_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub frameworks: Vec<FrameworkBinding>,
    #[serde(default)]
    pub axes: ProfileAxes,
    #[serde(default)]
    pub routing_hints: RoutingHints,
    #[serde(default = "default_true")]
    pub use_derived_routing: bool,
    #[serde(default)]
    pub extensions: serde_json::Value,
}

fn default_schema_version() -> u32 {
    1
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FrameworkBinding {
    pub id: String,
    pub type_code: String,
    #[serde(default = "default_source")]
    pub source: String,
    #[serde(default = "default_confidence")]
    pub confidence: f32,
}

fn default_source() -> String {
    "user_selected".into()
}

fn default_confidence() -> f32 {
    1.0
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct ProfileAxes {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub extraversion: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub intuition: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub thinking: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub judging: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub initiative: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub coordination: Option<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct MemberProfileOverlay {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub routing_hints: Option<RoutingHints>,
    #[serde(default)]
    pub disabled_frameworks: Vec<String>,
}

/// 运行时合并结果（不落库）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EffectiveMemberProfile {
    pub routing_hints: RoutingHints,
    pub prompt_persona_block: String,
    pub capability_tags: Vec<String>,
    pub frameworks: Vec<FrameworkBinding>,
    pub initiative: InitiativeLevel,
    pub coordination: CoordinationLevel,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct ExtensionFieldSchema {
    #[serde(rename = "type")]
    pub r#type: String,
    #[serde(default, rename = "enum")]
    pub enum_values: Vec<serde_json::Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_length: Option<usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct ExtensionsSchema {
    #[serde(default)]
    pub properties: std::collections::HashMap<String, ExtensionFieldSchema>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProfileTypeDefinition {
    pub type_code: String,
    pub label_zh: String,
    #[serde(default)]
    pub axis_defaults: ProfileAxes,
    #[serde(default)]
    pub default_routing_hints: RoutingHints,
    #[serde(default)]
    pub prompt_snippet: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProfileFrameworkCatalog {
    pub id: String,
    pub name: String,
    pub version: String,
    #[serde(default)]
    pub types: Vec<ProfileTypeDefinition>,
    /// 绑定此 framework 时，profile.extensions 可选字段校验。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub extensions_schema: Option<ExtensionsSchema>,
}

/// 群 Bundle 中成员画像摘要。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MemberProfileSummary {
    pub friend_id: String,
    pub initiative: InitiativeLevel,
    pub coordination: CoordinationLevel,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub framework_labels: Vec<String>,
}
