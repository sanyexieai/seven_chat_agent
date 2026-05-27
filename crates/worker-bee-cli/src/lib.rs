//! Worker Bee（工蜂）CLI 库：参考 codex exec，内置 memory / MCP / skill。

pub mod cli;
pub mod cli_blocks;
pub mod codex_jsonl;
pub mod exec;
pub mod jsonl;
pub mod memory;
pub mod mcp;
pub mod skill;

/// honeycomb Pty 预设名。
pub const WORKER_BEE_CLI_PRESET: &str = "worker-bee-cli";

/// 安装到 PATH 的二进制名。
pub const WORKER_BEE_CLI_BIN: &str = "worker-bee";

pub use cli::run;
pub use cli_blocks::{
    apply_cli_block_delta, cli_blocks_to_plain, parse_cli_blocks_json, parse_codex_exec_jsonl_to_blocks,
    parse_codex_thread_id_from_jsonl, stream_split_cli_delta, CliBlock, CliBlockDelta,
    CodexExecJsonlBlockParser, CommandRunStatus, TodoItem,
};
pub use codex_jsonl::{parse_codex_exec_jsonl_to_display, CodexExecJsonlDisplayParser};
pub use exec::ExecOptions;

#[cfg(test)]
mod tests {
    use super::jsonl::emit_agent_message;

    #[test]
    fn agent_message_jsonl_shape() {
        let line = emit_agent_message("你好");
        let v: serde_json::Value = serde_json::from_str(&line).unwrap();
        assert_eq!(v["type"], "item.completed");
        assert_eq!(v["item"]["type"], "agent_message");
        assert_eq!(v["item"]["text"], "你好");
    }
}
