use std::time::{Duration, Instant};

use dashmap::DashMap;
use parking_lot::Mutex;
use tracing::debug;

use crate::Result;

#[derive(Debug)]
struct LimitState {
    last_refill: Instant,
    tokens: f64,
}

#[derive(Default)]
pub struct RateLimiter {
    buckets: DashMap<String, Mutex<LimitState>>,
}

impl RateLimiter {
    pub fn new() -> Self {
        Self::default()
    }

    pub async fn acquire(&self, key_id: &str, rpm_limit: Option<i64>) -> Result<()> {
        let rpm = match rpm_limit {
            Some(r) if r > 0 => r as f64,
            _ => return Ok(()),
        };
        let max = rpm.max(1.0);
        let per_sec = rpm / 60.0;
        loop {
            let wait = {
                let entry = self
                    .buckets
                    .entry(key_id.to_string())
                    .or_insert_with(|| Mutex::new(LimitState {
                        last_refill: Instant::now(),
                        tokens: max,
                    }));
                let mut state = entry.lock();
                let now = Instant::now();
                let elapsed = now.duration_since(state.last_refill).as_secs_f64();
                state.tokens = (state.tokens + elapsed * per_sec).min(max);
                state.last_refill = now;
                if state.tokens >= 1.0 {
                    state.tokens -= 1.0;
                    None
                } else {
                    let deficit = 1.0 - state.tokens;
                    Some(deficit / per_sec)
                }
            };
            match wait {
                None => return Ok(()),
                Some(secs) => {
                    let wait_ms = (secs * 1000.0).clamp(50.0, 5000.0) as u64;
                    debug!(key = key_id, wait_ms, "rate-limited, sleeping");
                    tokio::time::sleep(Duration::from_millis(wait_ms)).await;
                }
            }
        }
    }
}
