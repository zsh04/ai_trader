#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/build_ui.sh <tag> [<tag> ...] [--context <dir>]

Build the UI Docker image (Streamlit) with one or more tags. Context defaults to repo root.
USAGE
}

context="."
image_tags=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --context)
      shift
      context=${1:-.}
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      image_tags+=("$1")
      ;;
  esac
  shift || break
  done

if [[ ${#image_tags[@]} -eq 0 ]]; then
  usage
  exit 1
fi

echo "[build] building UI image (${image_tags[*]}) (context: ${context})"

build_cmd=(docker build -f infra/docker/Dockerfile.ui)
if [[ -n "${APP_VERSION:-}" ]]; then
  build_cmd+=(--build-arg "APP_VERSION=${APP_VERSION}" --label "org.opencontainers.image.version=${APP_VERSION}")
fi
for tag in "${image_tags[@]}"; do
  build_cmd+=(-t "$tag")
 done
build_cmd+=("${context}")

printf '[build] docker %s\n' "${build_cmd[*]}"
"${build_cmd[@]}"

echo "[build] done"
