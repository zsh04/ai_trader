#!/usr/bin/env bash
set -euo pipefail

REGISTRY="aitraderacr.azurecr.io"
IMAGE_NAME="ai-trader-consumer"
TAG="${1:-$(date +%Y%m%d.%H%M)-amd64}"
IMAGE_REF="${REGISTRY}/${IMAGE_NAME}:${TAG}"

echo "[build-consumer-local] building ${IMAGE_REF}"
docker buildx build \
  --platform linux/amd64 \
  -f workers/consumer/Dockerfile \
  -t "${IMAGE_REF}" \
  .

echo "[build-consumer-local] pushing ${IMAGE_REF}"
docker push "${IMAGE_REF}"

echo "${IMAGE_REF}"
