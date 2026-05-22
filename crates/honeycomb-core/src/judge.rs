// Lightweight judge helpers used by the scheduler in M3.

use crate::agent::Judgment;

pub fn parse_lenient(text: &str) -> Option<Judgment> {
    serde_json::from_str(text).ok()
}
