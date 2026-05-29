pub const PRESET_CODEX: &str = "codex-exec";
pub const PRESET_CURSOR: &str = "cursor";
pub const PRESET_CLAUDE: &str = "claude";
pub const PRESET_WORKER_BEE: &str = "worker-bee-cli";

pub const EXTERNAL_CLI_PRESETS: &[&str] = &[PRESET_CLAUDE, PRESET_CODEX, PRESET_CURSOR];

pub fn is_external_cli_preset(preset: Option<&str>) -> bool {
    preset.is_some_and(|p| EXTERNAL_CLI_PRESETS.contains(&p))
}

pub fn is_worker_bee_preset(preset: Option<&str>) -> bool {
    preset == Some(PRESET_WORKER_BEE)
}

pub fn uses_codex_exec_protocol(preset: &str) -> bool {
    preset == PRESET_CODEX || preset == PRESET_WORKER_BEE
}
