use crate::types::Judgment;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct JudgmentRaw {
    #[serde(default)]
    should_reply: bool,
    #[serde(default)]
    confidence: f32,
    #[serde(default)]
    reason: Option<String>,
    #[serde(default)]
    suggested_delay_ms: u64,
}

impl JudgmentRaw {
    fn into_judgment(self) -> Judgment {
        Judgment {
            should_reply: self.should_reply,
            confidence: self.confidence,
            reason: self.reason,
            suggested_delay_ms: self.suggested_delay_ms,
            source: None,
        }
    }
}

pub fn parse_lenient(text: &str) -> Option<Judgment> {
    serde_json::from_str::<JudgmentRaw>(text)
        .ok()
        .map(|r| r.into_judgment())
        .or_else(|| {
            extract_json(text)
                .and_then(|body| serde_json::from_str::<JudgmentRaw>(&body).ok())
                .map(|r| r.into_judgment())
        })
}

pub fn parse_llm_response(text: &str) -> Judgment {
    parse_lenient(text).unwrap_or(Judgment {
        should_reply: false,
        confidence: 0.0,
        reason: Some("judge parse failed".into()),
        suggested_delay_ms: 0,
        source: None,
    })
}

fn extract_json(text: &str) -> Option<String> {
    let start = text.find('{')?;
    let end = text.rfind('}')?;
    if end >= start {
        Some(text[start..=end].to_string())
    } else {
        None
    }
}
