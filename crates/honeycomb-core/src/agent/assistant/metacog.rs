use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReflectionEntry {
    pub score: f32,
    pub summary: String,
    pub lessons: Vec<String>,
}
