#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

command=${1:-}
shift || true

log() { echo "[dev] $*"; }
die() { echo "[dev] error: $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: ./scripts/dev.sh <command>

Commands:
  mkvenv       Create .venv and install dependencies
  install      Install/upgrade dependencies inside existing .venv
  fmt          Run formatters (ruff --fix, black)
  lint         Run ruff lint
  test         Run pytest -q
  run          Run uvicorn (dev server)
  pm2-up       pm2 start ecosystem.config.cjs --only ai_trader,pm2-logrotate
  ngrok-up     pm2 start ecosystem.config.cjs --only ngrok
  webhook-set  ./scripts/set_webhook.sh
EOF
}

ensure_venv() {
  if [[ ! -d ".venv" ]]; then
    die ".venv missing; run ./scripts/dev.sh mkvenv first"
  fi
  source .venv/bin/activate
}

case "$command" in
  mkvenv)
    log "creating virtualenv"
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    ;;
  install)
    ensure_venv
    log "installing requirements"
    pip install --upgrade pip
    pip install -r requirements.txt
    ;;
  fmt)
    ensure_venv
    log "running ruff --fix"
    ruff check . --fix
    log "running black"
    black .
    ;;
  lint)
    ensure_venv
    log "running ruff lint"
    ruff check .
    ;;
  test)
    ensure_venv
    log "running pytest -q"
    pytest -q
    ;;
  run)
    ensure_venv
    log "starting uvicorn"
    uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  pm2-up)
    log "starting pm2 apps"
    LOG_DIR=${LOG_DIR:-$HOME/ai_trader_logs} pm2 start ecosystem.config.cjs --only ai_trader,pm2-logrotate
    ;;
  ngrok-up)
    log "starting pm2 ngrok"
    pm2 start ecosystem.config.cjs --only ngrok
    ;;
  webhook-set)
    ensure_venv
    log "setting webhook"
    bash ./scripts/set_webhook.sh
    ;;
  ""|-h|--help)
    usage
    ;;
  *)
    usage
    die "unknown command: $command"
    ;;
esac
