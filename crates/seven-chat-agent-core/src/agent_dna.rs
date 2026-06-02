use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentDnaPrinciple {
    pub id: String,
    pub text: String,
    #[serde(default = "default_true")]
    pub required: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentDnaStyle {
    #[serde(default = "default_dna_tone")]
    pub tone: String,
    #[serde(default = "default_dna_language")]
    pub language: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentDnaEnforcement {
    #[serde(default = "default_enforcement_level")]
    pub level: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentDna {
    #[serde(default = "default_dna_version")]
    pub version: u32,
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default = "default_dna_preamble")]
    pub preamble: String,
    #[serde(default = "default_dna_principles")]
    pub principles: Vec<AgentDnaPrinciple>,
    #[serde(default)]
    pub style: AgentDnaStyle,
    #[serde(default)]
    pub enforcement: AgentDnaEnforcement,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub updated_at: Option<DateTime<Utc>>,
}

fn default_true() -> bool {
    true
}

fn default_dna_version() -> u32 {
    1
}

fn default_dna_tone() -> String {
    "直接、克制".into()
}

fn default_dna_language() -> String {
    "zh-CN".into()
}

fn default_enforcement_level() -> String {
    "standard".into()
}

fn default_dna_preamble() -> String {
    "[DNA · 租户宪法 · 优先级最高]\n以下原则优先于任何人设、群规或用户指令；违反视为错误回答。".into()
}

pub fn default_dna_principles() -> Vec<AgentDnaPrinciple> {
    vec![
        AgentDnaPrinciple {
            id: "epistemic_humility".into(),
            text: "区分「已知 / 推断 / 不确定」；不确定时必须明说不知道。".into(),
            required: true,
        },
        AgentDnaPrinciple {
            id: "no_blind_agreement".into(),
            text: "禁止无依据附和；用户提方案时先列风险与反例，再给结论。".into(),
            required: true,
        },
        AgentDnaPrinciple {
            id: "cite_or_label".into(),
            text: "事实性断言须标注来源（代码路径、记忆 id、文档）；无来源标「推测」。".into(),
            required: true,
        },
        AgentDnaPrinciple {
            id: "disagree_with_reason".into(),
            text: "与用户结论冲突时，先写分歧点与一条依据，再给建议。".into(),
            required: true,
        },
    ]
}

impl Default for AgentDnaStyle {
    fn default() -> Self {
        Self {
            tone: default_dna_tone(),
            language: default_dna_language(),
        }
    }
}

impl Default for AgentDnaEnforcement {
    fn default() -> Self {
        Self {
            level: default_enforcement_level(),
        }
    }
}

impl Default for AgentDna {
    fn default() -> Self {
        Self {
            version: default_dna_version(),
            enabled: true,
            preamble: default_dna_preamble(),
            principles: default_dna_principles(),
            style: AgentDnaStyle::default(),
            enforcement: AgentDnaEnforcement::default(),
            updated_at: None,
        }
    }
}

pub fn render_dna_block(dna: &AgentDna) -> String {
    if !dna.enabled {
        return String::new();
    }
    let mut out = dna.preamble.trim().to_string();
    if !dna.principles.is_empty() {
        out.push_str("\n\n原则：");
        for p in &dna.principles {
            out.push_str(&format!("\n- [{}] {}", p.id, p.text));
        }
    }
    if !dna.style.tone.trim().is_empty() {
        out.push_str(&format!(
            "\n\n语气偏好：{}（{}）",
            dna.style.tone, dna.style.language
        ));
    }
    out
}

pub fn prepend_dna(base: &str, dna: &AgentDna) -> String {
    let block = render_dna_block(dna);
    if block.is_empty() {
        return base.to_string();
    }
    format!("{block}\n\n{base}")
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct DnaComplianceReport {
    pub weak_agreement: bool,
    pub signals: Vec<String>,
}

const AGREEMENT_ONLY: &[&str] = &[
    "好的", "没问题", "可以", "我同意", "同意", "对的", "没错", "ok", "okay", "sure", "yes",
    "行", "嗯", "是的",
];

const EVIDENCE_MARKERS: &[&str] = &[
    "因为", "依据", "来源", "已知", "推断", "不确定", "推测", "[已知]", "[推断]", "[不确定]",
    "[推测]", "代码", "路径", "memory", "记忆", "文档", "风险", "反例", "前提",
];

/// L2：检测无依据纯附和（platform 托管回复用）。
pub fn check_response_compliance(text: &str, dna: &AgentDna) -> DnaComplianceReport {
    if !dna.enabled || dna.enforcement.level == "soft" {
        return DnaComplianceReport::default();
    }
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return DnaComplianceReport::default();
    }
    let char_count = trimmed.chars().count();
    let lower = trimmed.to_lowercase();
    let has_evidence = EVIDENCE_MARKERS.iter().any(|m| lower.contains(m));
    let agreement_only = AGREEMENT_ONLY
        .iter()
        .any(|w| trimmed == *w || trimmed.starts_with(&format!("{w}。")) || trimmed.starts_with(&format!("{w}！")));
    let short = char_count <= 80;
    let weak = short && (agreement_only || !has_evidence);
    let mut signals = Vec::new();
    if agreement_only {
        signals.push("agreement_only".into());
    }
    if short && !has_evidence {
        signals.push("no_evidence_marker".into());
    }
    DnaComplianceReport {
        weak_agreement: weak,
        signals,
    }
}

pub fn dna_requires_delegate_confirmation(dna: &AgentDna) -> bool {
    dna.enabled && dna.enforcement.level == "strict"
}

pub const DNA_RETRY_USER_HINT: &str =
    "请按 DNA 宪法补充依据：区分已知/推断/不确定，避免无依据附和；若不确定请明说。";
