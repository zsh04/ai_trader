#!/usr/bin/env zsh
set -euo pipefail

APP_VERSION=${APP_VERSION:-dev}
HF_COMMIT_SHA=${HF_COMMIT_SHA:-main}
ADAPTER_TAG=${ADAPTER_TAG:-base}
SPRINT_TAG=${SPRINT_TAG:-sprint-$(date -u +%y%V)}
IMAGE_TAG=${IMAGE_TAG:-${SPRINT_TAG}}
ACR_NAME=${ACR_NAME:-}
PYTHON_VERSION=${PYTHON_VERSION:-3.12}
BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)

build_image() {
  local service=$1
  local dockerfile=$2
  local image_name="ai-trader-${service}"
  docker build \
    -f "$dockerfile" \
    --build-arg PYTHON_VERSION="${PYTHON_VERSION}" \
    --build-arg APP_VERSION="${APP_VERSION}" \
    --build-arg HF_COMMIT_SHA="${HF_COMMIT_SHA}" \
    --build-arg ADAPTER_TAG="${ADAPTER_TAG}" \
    --build-arg BUILD_DATE="${BUILD_DATE}" \
    -t "${image_name}:latest" \
    -t "${image_name}:${IMAGE_TAG}" \
    .

  if [[ -n "${ACR_NAME}" ]]; then
    local registry="${ACR_NAME}.azurecr.io/${image_name}"
    docker tag "${image_name}:latest" "${registry}:latest"
    docker tag "${image_name}:${IMAGE_TAG}" "${registry}:${IMAGE_TAG}"
  fi
}

push_image() {
  local service=$1
  local image_name="ai-trader-${service}"
  if [[ -z "${ACR_NAME}" ]]; then
    return
  fi
  local registry="${ACR_NAME}.azurecr.io/${image_name}"
  az acr login --name "${ACR_NAME}"
  docker push "${registry}:latest"
  docker push "${registry}:${IMAGE_TAG}"
}

build_image "nlp" models/finbert/Dockerfile
build_image "forecast" models/chronos2/Dockerfile
build_image "sweep" jobs/sweep/Dockerfile
push_image "nlp"
push_image "forecast"
push_image "sweep"
