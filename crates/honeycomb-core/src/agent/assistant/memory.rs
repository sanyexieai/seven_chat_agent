use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssistantMemory {
    pub kind: String,
    pub content: String,
    pub weight: f32,
}
