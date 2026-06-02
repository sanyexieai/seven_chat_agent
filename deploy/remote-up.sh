#!/usr/bin/env bash
# 在目标服务器上拉取镜像并重启服务（由 GitHub Actions SSH 调用，也可手动执行）
# 用法: IMAGE_TAG=v2.0.0 bash remote-up.sh [server|cli-relay|all]

set -euo pipefail

SERVICE="${1:-cli-relay}"
REGISTRY="${REGISTRY:-3ye.co:9443}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"

# 去掉常见前缀 v / cli-relay/
VERSION="${IMAGE_TAG#cli-relay/}"
VERSION="${VERSION#v}"

export SERVER_IMAGE="${REGISTRY}/seven-chat-agent/server:${VERSION}"
export CLI_RELAY_IMAGE="${REGISTRY}/seven-chat-agent/cli-relay:${VERSION}"

cd "$DEPLOY_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -n "${REGISTRY_USERNAME:-}" ]] && [[ -n "${REGISTRY_PASSWORD:-}" ]]; then
  echo "Logging in to ${REGISTRY}..."
  echo "${REGISTRY_PASSWORD}" | docker login "${REGISTRY}" -u "${REGISTRY_USERNAME}" --password-stdin
fi

echo "Deploy ${SERVICE} — server=${SERVER_IMAGE} relay=${CLI_RELAY_IMAGE}"

case "$SERVICE" in
  server)
    docker compose pull server
    docker compose up -d server
    ;;
  cli-relay)
    docker compose --profile relay pull cli-relay
    docker compose --profile relay up -d cli-relay
    ;;
  all)
    docker compose --profile relay pull
    docker compose --profile relay up -d
    ;;
  *)
    echo "Unknown service: $SERVICE (use server|cli-relay|all)" >&2
    exit 1
    ;;
esac

docker compose ps
echo "Done."
