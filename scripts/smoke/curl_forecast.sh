#!/usr/bin/env bash
set -euo pipefail

HOST=${HOST:-http://ai-trader-forecast.internal}

curl -fsSL "$HOST/healthz"
echo
curl -fsSL "$HOST/ready" || true
echo
curl -fsSL -X POST "$HOST/forecast" \
  -H 'Content-Type: application/json' \
  -d '{"series": [100, 101, 102.5, 103.2], "horizon": 4}'
echo
