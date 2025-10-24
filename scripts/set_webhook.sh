#!/usr/bin/env zsh
set -euo pipefail

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required}"
: "${TELEGRAM_WEBHOOK_SECRET:?TELEGRAM_WEBHOOK_SECRET is required}"

NGROK_API="http://127.0.0.1:4040/api/tunnels"

echo "==> Resolving public https URL from ngrok..."
if command -v jq >/dev/null 2>&1; then
  PUBLIC_URL="$(curl -s "$NGROK_API" | jq -r '.tunnels[] | select(.proto=="https") | .public_url' | head -n1)"
else
  PUBLIC_URL="$(curl -s "$NGROK_API" | sed -n 's/.*"public_url":"\([^"]*\)".*/\1/p' | grep '^https://' | head -n1)"
fi

if [[ -z "${PUBLIC_URL:-}" ]]; then
  echo "error: ngrok public_url not found. Is ngrok running?" >&2
  exit 1
fi
WEBHOOK_URL="${PUBLIC_URL}/telegram/webhook"
echo "==> Setting Telegram webhook → ${WEBHOOK_URL}"

curl -sS -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "url": "${WEBHOOK_URL}",
  "secret_token": "${TELEGRAM_WEBHOOK_SECRET}",
  "drop_pending_updates": true,
  "max_connections": 40
}
JSON

echo "✓ Webhook set."