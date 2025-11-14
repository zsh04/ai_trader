#!/usr/bin/env bash
set -euo pipefail

HOST=${HOST:-http://ai-trader-nlp.internal}

curl -fsSL "$HOST/healthz"
echo
curl -fsSL "$HOST/ready" || true
echo
curl -fsSL -X POST "$HOST/classify-sentiment" \
  -H 'Content-Type: application/json' \
  -d '{"text": "Market breadth improves on dovish guidance."}'
echo
