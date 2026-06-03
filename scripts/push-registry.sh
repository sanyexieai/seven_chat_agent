#!/usr/bin/env bash
# 构建 server / cli-relay 镜像并推送到私有仓库，同时打版本 tag 与 latest。
#
# 用法:
#   scripts/push-registry.sh              # 读取 deploy/.image-version，patch +1 后构建推送
#   scripts/push-registry.sh 2.0.3        # 指定版本（不自动 +1，除非加 --bump）
#   scripts/push-registry.sh --bump       # 在 .image-version 基础上 patch +1
#   scripts/push-registry.sh --server-only
#   scripts/push-registry.sh --dry-run
#
# 环境（优先 deploy/.env，其次 deploy/.env.registry）:
#   REGISTRY=3ye.co:9443
#   REGISTRY_USERNAME / REGISTRY_PASSWORD
#   IMAGE_NAMESPACE=seven-chat-agent
#
# 版本文件: deploy/.image-version（推送成功后写回）

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY="$ROOT/deploy"
VERSION_FILE="$DEPLOY/.image-version"

REGISTRY="${REGISTRY:-3ye.co:9443}"
IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-seven-chat-agent}"
BUILD_SERVER=1
BUILD_RELAY=1
DRY_RUN=0
DO_BUMP=0
EXPLICIT_VERSION=""
BUMP_KIND="patch"

usage() {
  cat <<'EOF'
用法: scripts/push-registry.sh [选项] [版本]

  无参数        读取 deploy/.image-version，patch 版本 +1，构建并推送
  2.0.3 / v2.0.3  使用指定版本（默认不 bump 文件；加 --bump 会先 +1 再与参数取较大逻辑见下）

选项:
  --bump              在 .image-version 基础上递增（默认 patch；见 --bump-minor/major）
  --bump-minor        递增 minor，patch 归零
  --bump-major        递增 major，minor/patch 归零
  --server-only       仅 server 镜像
  --relay-only        仅 cli-relay 镜像
  --dry-run           只打印将执行的命令，不构建/推送
  -h, --help          显示帮助

环境变量 / deploy/.env:
  REGISTRY              默认 3ye.co:9443
  REGISTRY_USERNAME     仓库登录用户
  REGISTRY_PASSWORD     仓库密码或 token
  IMAGE_NAMESPACE       默认 seven-chat-agent

示例:
  scripts/push-registry.sh
  scripts/push-registry.sh 2.1.0
  scripts/push-registry.sh --bump --server-only
  REGISTRY_PASSWORD=xxx scripts/push-registry.sh --dry-run
EOF
}

load_env() {
  for f in "$DEPLOY/.env" "$DEPLOY/.env.registry"; do
    if [[ -f "$f" ]]; then
      set -a
      # shellcheck disable=SC1090
      source "$f"
      set +a
    fi
  done
  REGISTRY="${REGISTRY:-3ye.co:9443}"
  IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-seven-chat-agent}"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少命令: $1" >&2
    exit 1
  }
}

normalize_version() {
  local v="${1#v}"
  v="${v#V}"
  if [[ ! "$v" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.+][0-9A-Za-z.-]*)?$ ]]; then
    echo "无效版本号（期望 semver 如 2.0.1）: $1" >&2
    exit 1
  fi
  # 镜像 tag 仅用主版本号三段
  if [[ "$v" =~ ^([0-9]+\.[0-9]+\.[0-9]+) ]]; then
    echo "${BASH_REMATCH[1]}"
  else
    echo "$v"
  fi
}

read_stored_version() {
  if [[ -f "$VERSION_FILE" ]]; then
    tr -d ' \n\r' <"$VERSION_FILE"
    return
  fi
  if [[ -f "$ROOT/Cargo.toml" ]]; then
    awk -F'"' '/^version = / { print $2; exit }' "$ROOT/Cargo.toml"
    return
  fi
  echo "2.0.0"
}

bump_version() {
  local v="$1"
  local kind="$2"
  if [[ ! "$v" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    echo "无法递增版本: $v" >&2
    exit 1
  fi
  local major="${BASH_REMATCH[1]}"
  local minor="${BASH_REMATCH[2]}"
  local patch="${BASH_REMATCH[3]}"
  case "$kind" in
    major) echo "$((major + 1)).0.0" ;;
    minor) echo "${major}.$((minor + 1)).0" ;;
    patch|*) echo "${major}.${minor}.$((patch + 1))" ;;
  esac
}

write_version_file() {
  local v="$1"
  if [[ "$DRY_RUN" == 1 ]]; then
    echo "[dry-run] 将写入 $VERSION_FILE -> $v"
    return
  fi
  printf '%s\n' "$v" >"$VERSION_FILE"
}

registry_login() {
  if [[ -z "${REGISTRY_USERNAME:-}" || -z "${REGISTRY_PASSWORD:-}" ]]; then
    echo "未设置 REGISTRY_USERNAME / REGISTRY_PASSWORD，跳过 docker login（需已登录 ${REGISTRY}）"
    return 0
  fi
  echo "登录镜像仓库 ${REGISTRY} ..."
  if [[ "$DRY_RUN" == 1 ]]; then
    echo "[dry-run] docker login ${REGISTRY} -u ***"
    return 0
  fi
  echo "${REGISTRY_PASSWORD}" | docker login "${REGISTRY}" -u "${REGISTRY_USERNAME}" --password-stdin
}

build_and_push() {
  local name="$1"
  local dockerfile="$2"
  local image="${REGISTRY}/${IMAGE_NAMESPACE}/${name}"
  local version_tag="${image}:${VERSION}"
  local latest_tag="${image}:latest"

  echo ""
  echo "═══ ${name} ═══"
  echo "  构建: ${version_tag}"
  if [[ "$DRY_RUN" == 1 ]]; then
    echo "[dry-run] docker build -f ${dockerfile} -t ${version_tag} ${ROOT}"
    echo "[dry-run] docker tag ${version_tag} ${latest_tag}"
    echo "[dry-run] docker push ${version_tag}"
    echo "[dry-run] docker push ${latest_tag}"
    return 0
  fi

  docker build -f "${dockerfile}" -t "${version_tag}" "${ROOT}"
  docker tag "${version_tag}" "${latest_tag}"
  docker push "${version_tag}"
  docker push "${latest_tag}"
  echo "已推送: ${version_tag}"
  echo "已推送: ${latest_tag}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --bump) DO_BUMP=1; shift ;;
    --bump-minor) DO_BUMP=1; BUMP_KIND="minor"; shift ;;
    --bump-major) DO_BUMP=1; BUMP_KIND="major"; shift ;;
    --server-only) BUILD_RELAY=0; shift ;;
    --relay-only) BUILD_SERVER=0; shift ;;
    -*) echo "未知选项: $1" >&2; usage >&2; exit 1 ;;
    *)
      if [[ -n "$EXPLICIT_VERSION" ]]; then
        echo "多余参数: $1" >&2
        exit 1
      fi
      EXPLICIT_VERSION="$1"
      shift
      ;;
  esac
done

load_env
need_cmd docker

STORED="$(normalize_version "$(read_stored_version)")"

if [[ -n "$EXPLICIT_VERSION" ]]; then
  VERSION="$(normalize_version "$EXPLICIT_VERSION")"
  if [[ "$DO_BUMP" == 1 ]]; then
    BUMPED="$(bump_version "$STORED" "$BUMP_KIND")"
    echo "提示: 已指定版本 ${VERSION}，--bump 忽略（若需基于文件递增请勿传版本参数）" >&2
  fi
elif [[ "$DO_BUMP" == 1 ]]; then
  VERSION="$(bump_version "$STORED" "$BUMP_KIND")"
else
  # 默认：无参数时在文件版本上 patch +1
  VERSION="$(bump_version "$STORED" "patch")"
fi

if [[ "$BUILD_SERVER" == 0 && "$BUILD_RELAY" == 0 ]]; then
  echo "请至少构建 server 或 cli-relay" >&2
  exit 1
fi

SERVER_IMAGE="${REGISTRY}/${IMAGE_NAMESPACE}/server:${VERSION}"
RELAY_IMAGE="${REGISTRY}/${IMAGE_NAMESPACE}/cli-relay:${VERSION}"

echo "镜像仓库: ${REGISTRY}"
echo "命名空间: ${IMAGE_NAMESPACE}"
echo "版本标签: ${VERSION}（文件记录: ${STORED}）"
[[ "$BUILD_SERVER" == 1 ]] && echo "  server     -> ${SERVER_IMAGE} + :latest"
[[ "$BUILD_RELAY" == 1 ]] && echo "  cli-relay  -> ${RELAY_IMAGE} + :latest"

registry_login

if [[ "$BUILD_SERVER" == 1 ]]; then
  build_and_push "server" "$ROOT/docker/server/Dockerfile"
fi
if [[ "$BUILD_RELAY" == 1 ]]; then
  build_and_push "cli-relay" "$ROOT/docker/cli-relay/Dockerfile"
fi

write_version_file "$VERSION"

echo ""
echo "完成。版本 ${VERSION} 与 latest 已推送。"
echo "部署示例:"
echo "  cd deploy && IMAGE_TAG=${VERSION} bash remote-up.sh server"
if [[ "$DRY_RUN" == 0 ]]; then
  echo "已更新 ${VERSION_FILE}，可提交: git add deploy/.image-version && git commit -m \"chore: image version ${VERSION}\""
fi
