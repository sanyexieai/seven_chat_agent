#!/usr/bin/env bash
# 本地 Docker 开发：Docker 镜像仅在 Dockerfile 变更时重建；日常改代码后 compile + restart 即可。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY="$ROOT/deploy"
COMPOSE=(docker compose -f "$DEPLOY/docker-compose.local.yml" --project-directory "$DEPLOY")
MARKER="$DEPLOY/.local-docker/runtime-image.id"
STAGING_BIN="$DEPLOY/.local-docker/bin/seven-chat-agent-server"
DOCKERFILE="$ROOT/docker/server/Dockerfile.local"
CONTAINER_NAME="seven-chat-agent-server-local"

# release（默认）| debug（编译更快：FAST=1）
PROFILE="${PROFILE:-release}"
if [[ "${FAST:-}" == "1" ]]; then
  PROFILE=debug
fi

usage() {
  cat <<'EOF'
用法: scripts/local-docker.sh <命令> [选项]

  up          首次/启动：必要时构建运行时镜像，编译 server+web，启动容器
  refresh     改代码后：重新编译并 restart（不重建 Docker 镜像）
  restart     仅重启容器（已编译过）
  down        停止并移除容器（保留数据卷）
  logs        查看 server 日志
  build-image 强制重建运行时镜像（仅 Dockerfile.local 变更时需要）
  build-app   仅在本机编译 server + web，不操作容器

环境变量:
  FAST=1      使用 debug 版 server（编译更快）
  PROFILE=debug|release

说明:
  - 数据在卷 server-data-local，down 不会删除。
  - 配置: deploy/.env.local（可从 deploy/.env.local.example 复制）
  - 浏览器见启动后打印的地址（默认 0.0.0.0:18737 对局域网开放）
  - 仅本机访问: 在 deploy/.env.local 设 HOST_BIND=127.0.0.1
EOF
}

load_deploy_env() {
  if [[ -f "$DEPLOY/.env.local" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$DEPLOY/.env.local"
    set +a
  fi
}

print_access_urls() {
  load_deploy_env
  local port="${SERVER_PORT:-18737}"
  local bind="${HOST_BIND:-0.0.0.0}"
  echo ""
  echo "访问地址:"
  echo "  本机    http://127.0.0.1:${port}"
  if [[ "$bind" != "127.0.0.1" ]]; then
    local lan_ip=""
    lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    if [[ -n "$lan_ip" ]]; then
      echo "  局域网  http://${lan_ip}:${port}"
    fi
    echo "  端口映射: ${bind}:${port} -> 容器:18737（docker port ${CONTAINER_NAME}）"
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少命令: $1" >&2
    exit 1
  }
}

ensure_env_local() {
  if [[ ! -f "$DEPLOY/.env.local" ]]; then
    if [[ -f "$DEPLOY/.env.local.example" ]]; then
      cp "$DEPLOY/.env.local.example" "$DEPLOY/.env.local"
      echo "已生成 deploy/.env.local（可按需编辑 API Key 等）"
    fi
  fi
}

server_binary_path() {
  if [[ "$PROFILE" == "debug" ]]; then
    echo "$ROOT/target/debug/seven-chat-agent-server"
  else
    echo "$ROOT/target/release/seven-chat-agent-server"
  fi
}

build_server() {
  need_cmd cargo
  echo ">> 编译 seven-chat-agent-server ($PROFILE)…"
  if [[ "$PROFILE" == "debug" ]]; then
    cargo build -p seven-chat-agent-server --manifest-path "$ROOT/Cargo.toml"
  else
    cargo build --release -p seven-chat-agent-server --manifest-path "$ROOT/Cargo.toml"
  fi
  local bin
  bin="$(server_binary_path)"
  [[ -x "$bin" ]] || {
    echo "未找到可执行文件: $bin" >&2
    exit 1
  }
}

build_web() {
  need_cmd npm
  echo ">> 构建 web/dist…"
  if [[ ! -d "$ROOT/web/node_modules" ]]; then
    npm ci --prefix "$ROOT/web" --no-bin-links
  fi
  npm run build --prefix "$ROOT/web"
  [[ -f "$ROOT/web/dist/index.html" ]] || {
    echo "web 构建失败: 缺少 web/dist/index.html" >&2
    exit 1
  }
}

stop_server_if_running() {
  if docker ps -q -f "name=^${CONTAINER_NAME}$" 2>/dev/null | grep -q .; then
    echo ">> 停止容器以便编译（避免 target 二进制 Text file busy）…"
    "${COMPOSE[@]}" stop server 2>/dev/null || true
  fi
}

install_server_binary() {
  local src
  src="$(server_binary_path)"
  mkdir -p "$(dirname "$STAGING_BIN")"
  cp -f "$src" "$STAGING_BIN"
  chmod +x "$STAGING_BIN"
}

# 用 ldd 快速检查 glibc，避免试跑 server 时长时间无输出像「卡住」
verify_binary_in_runtime_image() {
  need_cmd docker
  export_server_binary
  [[ -x "$STAGING_BIN" ]] || return 0
  if ! docker image inspect seven-chat-agent/server:local-runtime >/dev/null 2>&1; then
    return 0
  fi
  echo ">> 检查二进制与运行时镜像兼容性…"
  local out
  out="$(docker run --rm \
    -v "$STAGING_BIN:/tmp/seven-chat-agent-server:ro" \
    --entrypoint ldd \
    seven-chat-agent/server:local-runtime \
    /tmp/seven-chat-agent-server 2>&1 || true)"
  if ! echo "$out" | grep -qE 'GLIBC.*not found|version .GLIBC'; then
    return 0
  fi
  echo "错误: 宿主机编译的 server 与 Docker 运行时镜像不兼容（常见为 glibc 版本）。" >&2
  echo "$out" >&2
  echo "  请执行: $0 build-image && $0 refresh" >&2
  exit 1
}

build_app() {
  stop_server_if_running
  build_server
  build_web
  install_server_binary
}

runtime_image_fingerprint() {
  sha256sum "$DOCKERFILE" 2>/dev/null | awk '{print $1}' || echo "unknown"
}

should_build_image() {
  [[ "${FORCE_IMAGE:-}" == "1" ]] && return 0
  local fp current
  fp="$(runtime_image_fingerprint)"
  current=""
  [[ -f "$MARKER" ]] && current="$(cat "$MARKER")"
  [[ "$fp" != "$current" ]]
}

build_image() {
  need_cmd docker
  export_server_binary
  mkdir -p "$(dirname "$MARKER")"
  echo ">> 构建本地运行时镜像（不含 Rust/Node 编译）…"
  "${COMPOSE[@]}" build server
  runtime_image_fingerprint >"$MARKER"
  echo ">> 镜像已就绪: seven-chat-agent/server:local-runtime"
}

export_server_binary() {
  export SERVER_BINARY="$STAGING_BIN"
}

cmd_up() {
  need_cmd docker
  ensure_env_local
  export_server_binary
  if should_build_image; then
    build_image
  else
    echo ">> 跳过镜像构建（Dockerfile.local 未变，可用 build-image 强制重建）"
  fi
  build_app
  export_server_binary
  if [[ ! -x "$STAGING_BIN" ]]; then
    echo "缺少 staging 二进制: $STAGING_BIN" >&2
    exit 1
  fi
  verify_binary_in_runtime_image
  echo ">> 启动容器…"
  "${COMPOSE[@]}" up -d server
  print_access_urls
  echo "改代码后: $0 refresh"
  echo "（改过端口映射后请先: $0 down && $0 up）"
}

cmd_refresh() {
  need_cmd docker
  ensure_env_local
  export_server_binary
  build_app
  export_server_binary
  verify_binary_in_runtime_image
  echo ">> 启动容器…"
  "${COMPOSE[@]}" up -d server
  echo ">> 已重新编译并启动 server"
  print_access_urls
}

cmd_restart() {
  need_cmd docker
  ensure_env_local
  export_server_binary
  "${COMPOSE[@]}" restart server
}

cmd_down() {
  need_cmd docker
  export_server_binary
  "${COMPOSE[@]}" down
}

cmd_logs() {
  need_cmd docker
  export_server_binary
  "${COMPOSE[@]}" logs -f --tail=200 server
}

main() {
  local cmd="${1:-}"

  case "$cmd" in
    up) cmd_up ;;
    refresh|update) cmd_refresh ;;
    restart) cmd_restart ;;
    down) cmd_down ;;
    logs) cmd_logs ;;
    status)
      need_cmd docker
      export_server_binary
      "${COMPOSE[@]}" ps
      echo ""
      docker port "$CONTAINER_NAME" 2>/dev/null || echo "容器未运行"
      print_access_urls
      ;;
    build-image)
      FORCE_IMAGE=1 build_image
      ;;
    build-app) build_app ;;
    -h|--help|help|"") usage ;;
    *)
      echo "未知命令: $cmd" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
