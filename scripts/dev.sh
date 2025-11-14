#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

cmd=${1:-}
shift || true

log() { echo "[dev] $*"; }
die() { echo "[dev] error: $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: ./scripts/dev.sh <command>

Commands:
  mkvenv       Create .venv and install runtime + dev dependencies
  install      Install/upgrade dependencies inside existing .venv
  fmt          Run black auto-formatter
  lint         Run ruff lint and bandit security scan
  test         Run pytest test suite
EOF
}

ensure_venv() {
  if [[ ! -d ".venv" ]]; then
    die ".venv missing; run ./scripts/dev.sh mkvenv first"
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
}

case "$cmd" in
  mkvenv)
    if [[ ! -d ".venv" ]]; then
      log "creating virtualenv (.venv)"
      python3 -m venv .venv
    else
      log ".venv already exists"
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install --upgrade pip
    log "installing runtime + dev dependencies"
    pip install -r requirements-dev.txt
    ;;
  install)
    ensure_venv
    pip install --upgrade pip
    log "installing runtime + dev dependencies"
    pip install -r requirements-dev.txt
    ;;
  fmt)
    ensure_venv
    log "running black formatter"
    black .
    ;;
  lint)
    ensure_venv
    log "running ruff"
    ruff check .
    log "running bandit"
    bandit -q -r app scripts tests -s B101
    ;;
  test)
    ensure_venv
    log "running pytest"
    pytest "$@"
    ;;
  ""|-h|--help)
    usage
    ;;
  *)
    usage
    die "unknown command: $cmd"
    ;;
esac
