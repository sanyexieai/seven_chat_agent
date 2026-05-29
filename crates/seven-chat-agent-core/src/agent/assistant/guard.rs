use once_cell::sync::Lazy;
use regex::Regex;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct GuardReport {
    pub level: String,
    pub findings: Vec<GuardFinding>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardFinding {
    pub kind: String,
    pub pattern: String,
    pub excerpt: String,
}

static PATTERNS: Lazy<Vec<(&'static str, Regex, &'static str)>> = Lazy::new(|| {
    let mut p = Vec::new();
    let entries: &[(&str, &str, &str)] = &[
        ("dangerous_shell", r"(?i)\brm\s+-rf\s+/", "high"),
        ("dangerous_shell", r"(?i)\bmkfs\.|\bdd\s+if=", "high"),
        ("dangerous_shell", r"(?i)\bshutdown\b|\breboot\b|\bhalt\b", "high"),
        ("dangerous_shell", r"(?i)\bchmod\s+777\s+/", "high"),
        ("dangerous_shell", r"(?i)\biptables\b|\bnftables\b", "medium"),
        ("dangerous_shell", r"(?i)\bsystemctl\b\s+(stop|disable)\s+ssh", "high"),
        ("network_exfil", r"(?i)curl\s+[^|]*\|\s*sh", "high"),
        ("network_exfil", r"(?i)wget\s+[^|]*\|\s*bash", "high"),
        ("network_exfil", r"(?i)nc\s+-e\b", "high"),
        ("network_exfil", r"(?i)reverse\s+shell", "high"),
        ("credential_leak", r"(?i)AKIA[0-9A-Z]{16}", "high"),
        ("credential_leak", r"(?i)aws_secret_access_key", "high"),
        ("credential_leak", r"(?i)private[_\- ]key\s*[:=]", "high"),
        ("credential_leak", r"(?i)BEGIN\s+RSA\s+PRIVATE\s+KEY", "high"),
        ("credential_leak", r"(?i)sk-[A-Za-z0-9]{20,}", "high"),
        ("credential_leak", r"(?i)ghp_[A-Za-z0-9]{20,}", "high"),
        ("credential_leak", r"(?i)glpat-[A-Za-z0-9_\-]{20,}", "high"),
        ("path_traversal", r"\.\./\.\./\.\./", "medium"),
        ("path_traversal", r"(?i)\/etc\/(passwd|shadow|sudoers)", "high"),
        ("filesystem_destroy", r"(?i)\bfind\s+.*-delete\b", "medium"),
        ("filesystem_destroy", r"(?i)\brm\s+-rf\s+~", "high"),
        ("filesystem_destroy", r"(?i)\bsudo\s+rm\s+-rf", "high"),
        ("crypto_misuse", r"(?i)\beval\s*\(", "medium"),
        ("crypto_misuse", r"(?i)\bexec\s*\(.*input", "medium"),
        ("crypto_misuse", r"(?i)pickle\.loads\(", "medium"),
        ("crypto_misuse", r"(?i)yaml\.load\(\s*[^,]+\)", "medium"),
        ("crypto_misuse", r"(?i)os\.system\(", "medium"),
        ("crypto_misuse", r"(?i)subprocess\.\w+\(.*shell=True", "medium"),
        ("inject_prompt", r"(?i)ignore\s+previous\s+instructions", "medium"),
        ("inject_prompt", r"(?i)system\s+prompt\s+override", "medium"),
        ("inject_prompt", r"(?i)export\s+all\s+conversation", "medium"),
        ("inject_prompt", r"(?i)bypass\s+(skills_guard|policy)", "high"),
        ("dangerous_db", r"(?i)DROP\s+TABLE", "medium"),
        ("dangerous_db", r"(?i)TRUNCATE\s+TABLE", "medium"),
        ("dangerous_db", r"(?i)DELETE\s+FROM\s+\w+\s*;\s*$", "medium"),
        ("payment_action", r"(?i)transfer\s+\d+\s*(usd|cny|eth|btc)", "high"),
        ("payment_action", r"(?i)stripe\.charges\.create", "medium"),
        ("payment_action", r"(?i)wire\s+\$\s*\d+", "high"),
        ("malware_pattern", r"(?i)\bbase64\.b64decode\(.*\)\s*;\s*exec", "high"),
        ("malware_pattern", r"(?i)mimikatz", "high"),
        ("malware_pattern", r"(?i)keylog", "medium"),
        ("malware_pattern", r"(?i)ransom", "medium"),
    ];
    for (kind, pat, level) in entries {
        if let Ok(re) = Regex::new(pat) {
            p.push((*kind, re, *level));
        }
    }
    p
});

pub fn scan(content: &str) -> GuardReport {
    let mut findings = Vec::new();
    let mut level = "safe";
    for (kind, re, lvl) in PATTERNS.iter() {
        if let Some(m) = re.find(content) {
            let excerpt = excerpt_around(content, m.start(), m.end());
            findings.push(GuardFinding {
                kind: (*kind).into(),
                pattern: re.as_str().into(),
                excerpt,
            });
            level = pick_higher(level, lvl);
        }
    }
    GuardReport {
        level: level.into(),
        findings,
    }
}

fn pick_higher(a: &'static str, b: &'static str) -> &'static str {
    fn rank(s: &str) -> u8 {
        match s {
            "high" => 3,
            "medium" => 2,
            "low" => 1,
            _ => 0,
        }
    }
    if rank(b) > rank(a) {
        b
    } else {
        a
    }
}

fn excerpt_around(content: &str, start: usize, end: usize) -> String {
    let start = start.saturating_sub(40);
    let end = (end + 40).min(content.len());
    content
        .get(start..end)
        .unwrap_or("")
        .replace('\n', " ")
        .trim()
        .to_string()
}
