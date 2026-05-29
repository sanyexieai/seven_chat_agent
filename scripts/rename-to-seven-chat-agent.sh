#!/usr/bin/env bash
# 一次性将 honeycomb-* 目录/包名统一为 seven-chat-agent-*
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mv_if() {
  local from=$1 to=$2
  if [[ -d $from && ! -e $to ]]; then
    git mv "$from" "$to"
  fi
}

mv_if crates/seven-chat-agent-cli-relay-protocol crates/seven-chat-agent-cli-relay-protocol
mv_if crates/seven-chat-agent-cli-relay crates/seven-chat-agent-cli-relay
mv_if crates/seven-chat-agent-cli-protocol crates/seven-chat-agent-cli-protocol
mv_if crates/seven-chat-agent-cli-codex crates/seven-chat-agent-cli-codex
mv_if crates/seven-chat-agent-cli-claude crates/seven-chat-agent-cli-claude
mv_if crates/seven-chat-agent-cli-cursor crates/seven-chat-agent-cli-cursor
mv_if crates/seven-chat-agent-cli-worker-bee crates/seven-chat-agent-cli-worker-bee
mv_if crates/seven-chat-agent-cli crates/seven-chat-agent-cli
mv_if crates/seven-chat-agent-judge crates/seven-chat-agent-judge
mv_if crates/seven-chat-agent-core crates/seven-chat-agent-core
mv_if crates/seven-chat-agent-server crates/seven-chat-agent-server
mv_if crates/seven-chat-agent-tui crates/seven-chat-agent-tui
mv_if apps/seven-chat-agent-desktop apps/seven-chat-agent-desktop

python3 <<'PY'
from pathlib import Path

ROOT = Path(".")
SKIP = {".git", "target", "node_modules", "dist", ".cursor"}

def iter_files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not any(s in p.parts for s in SKIP):
            if p.suffix in {
                ".rs", ".toml", ".md", ".ts", ".tsx", ".json", ".sh", ".py",
            } or p.name in {".env.example", "Cargo.lock"}:
                yield p

REPLACEMENTS = [
    ("seven-chat-agent-cli-relay-protocol", "seven-chat-agent-cli-relay-protocol"),
    ("seven-chat-agent-cli-relay", "seven-chat-agent-cli-relay"),
    ("seven-chat-agent-cli-worker-bee", "seven-chat-agent-cli-worker-bee"),
    ("seven-chat-agent-cli-protocol", "seven-chat-agent-cli-protocol"),
    ("seven-chat-agent-cli-codex", "seven-chat-agent-cli-codex"),
    ("seven-chat-agent-cli-claude", "seven-chat-agent-cli-claude"),
    ("seven-chat-agent-cli-cursor", "seven-chat-agent-cli-cursor"),
    ("seven-chat-agent-desktop", "seven-chat-agent-desktop"),
    ("seven-chat-agent-server", "seven-chat-agent-server"),
    ("seven-chat-agent-core", "seven-chat-agent-core"),
    ("seven-chat-agent-judge", "seven-chat-agent-judge"),
    ("seven-chat-agent-tui", "seven-chat-agent-tui"),
    ("seven-chat-agent-cli", "seven-chat-agent-cli"),
    ("seven_chat_agent_cli_relay_protocol", "seven_chat_agent_cli_relay_protocol"),
    ("seven_chat_agent_cli_relay", "seven_chat_agent_cli_relay"),
    ("seven_chat_agent_cli_worker_bee", "seven_chat_agent_cli_worker_bee"),
    ("seven_chat_agent_cli_protocol", "seven_chat_agent_cli_protocol"),
    ("seven_chat_agent_cli_codex", "seven_chat_agent_cli_codex"),
    ("seven_chat_agent_cli_claude", "seven_chat_agent_cli_claude"),
    ("seven_chat_agent_cli_cursor", "seven_chat_agent_cli_cursor"),
    ("seven_chat_agent_desktop", "seven_chat_agent_desktop"),
    ("seven_chat_agent_server", "seven_chat_agent_server"),
    ("seven_chat_agent_core", "seven_chat_agent_core"),
    ("seven_chat_agent_judge", "seven_chat_agent_judge"),
    ("seven_chat_agent_cli", "seven_chat_agent_cli"),
    ("seven_chat_agent_tui", "seven_chat_agent_tui"),
    ("SevenChatAgent", "SevenChatAgent"),
    ("seven_chat_agent.db", "seven_chat_agent.db"),
    ("SEVEN_CHAT_AGENT_", "SEVEN_CHAT_AGENT_"),
    ("com.sanyexieai.seven-chat-agent", "com.sanyexieai.seven-chat-agent"),
    ("X-SevenChatAgent-Im-Secret", "X-Seven-Chat-Agent-Im-Secret"),
    ("Seven Chat Agent 多 Agent", "Seven Chat Agent 多 Agent"),
]

for path in iter_files():
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    orig = text
    for a, b in REPLACEMENTS:
        text = text.replace(a, b)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print("updated", path)
PY

echo "Rename done. Run: cargo check --workspace"
