#!/usr/bin/env bash
# 将本地 Rust v2 主线推送到 https://github.com/sanyexieai/seven_chat_agent
# 远程 main 为 v1（FastAPI）且已有 v1.0.x 标签时，需 --force-with-lease 覆盖 main。
set -euo pipefail
cd "$(dirname "$0")/.."

if ! git rev-parse --verify v2.0.0 >/dev/null 2>&1; then
  git tag v2.0.0
fi

echo "本地 main: $(git rev-parse --short main)"
echo "即将推送 main 与 tag v2.0.0 到 origin（seven_chat_agent）…"
git push --force-with-lease origin main
git push origin v2.0.0

echo "完成。请在 GitHub → Releases 从 CHANGELOG.md 创建 v2.0.0 Release。"
