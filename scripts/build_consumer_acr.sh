#!/usr/bin/env bash
set -euo pipefail

REGISTRY="aitraderacr"
IMAGE_NAME="ai-trader-consumer"
TAG=""
EXTRA_ARGS=()

usage() {
  cat <<'EOF'
Usage: scripts/build_consumer_acr.sh [--tag <value>] [additional az acr build args...]

Examples:
  scripts/build_consumer_acr.sh --tag consumer-123 --no-logs
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag|-t)
      TAG="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -z "${TAG}" ]]; then
  TAG="$(date +%Y%m%d.%H%M)-amd64"
fi

IMAGE_REF="${REGISTRY}.azurecr.io/${IMAGE_NAME}:${TAG}"
echo "[build-consumer-acr] submitting build for ${IMAGE_REF}"
az acr build \
  --registry "${REGISTRY}" \
  --image "${IMAGE_NAME}:${TAG}" \
  --file workers/consumer/Dockerfile \
  .

echo "${IMAGE_REF}"
