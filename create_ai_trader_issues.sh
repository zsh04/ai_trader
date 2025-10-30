#!/usr/bin/env zsh
set -e

REPO="zsh04/ai_trader"

echo "📋 Creating issues and auto-registering labels for $REPO …"

create_issue() {
  local title="$1"
  local body="$2"
  local labels=("${(@s/,/)3}")

  for lbl in "${labels[@]}"; do
    if ! gh label list --repo "$REPO" --json name -q '.[] | .name' | grep -qx "$lbl"; then
      echo "➕ Creating label: $lbl"
      gh label create "$lbl" --repo "$REPO" --color "0366d6" --description "Auto-generated label"
    fi
  done

  echo "🪶 Creating issue: $title"
  gh issue create --repo "$REPO" --title "$title" --body "$body" --label "${(j:,:)labels}"
}

create_issue "Unify watchlist imports to app.sources.*" \
"**AC:** domain/watchlist_service.py and callers load from app.sources.* only; no app.source.* refs.\nUnit tests updated.\n\n**Priority:** P0 • **Complexity:** M" \
"watchlist,P0"

create_issue "Standardize watchlist source function signatures" \
"**AC:** Each source module exports get_symbols(preferred: bool = False) -> list[str]. resolve_watchlist passes only supported kwargs.\n\n**Priority:** P0 • **Complexity:** M" \
"watchlist,P0"

create_issue "Deduplicate legacy watchlist service" \
"**AC:** Remove/merge app/services/watchlist_service.py into domain version.\n\n**Priority:** P1 • **Complexity:** S" \
"cleanup,P1"

create_issue "/watchlist returns symbols for all sources" \
"**AC:** /watchlist returns non-empty symbols for manual|auto|finviz|textlist.\nTests added.\n\n**Priority:** P0 • **Complexity:** M" \
"watchlist,P0"

create_issue "Telegram webhook auth: enforce + log" \
"**AC:** In prod, reject bad/missing secret with 401 + log. In non-prod allow if TELEGRAM_ALLOW_TEST_NO_SECRET=1.\n\n**Priority:** P1 • **Complexity:** S" \
"telegram,P1"

create_issue "CI container boot smoke" \
"**AC:** Post-build docker run + curl /health, /market, /telegram/webhook with fake secret.\nFail fast on non-200.\n\n**Priority:** P1 • **Complexity:** M" \
"ci,P1"

create_issue "Env schema validator" \
"**AC:** Single module validates env on startup, alias support TELEGRAM_TOKEN→TELEGRAM_BOT_TOKEN.\n\n**Priority:** P2 • **Complexity:** M" \
"infra,P2"

create_issue "Telegram 429 backoff test" \
"**AC:** Simulate Retry-After header; verify backoff and retry.\n\n**Priority:** P2 • **Complexity:** S" \
"telegram,P2"

create_issue "Router matrix test" \
"**AC:** Assert presence of /health/*, /telegram/webhook, /watchlist.\n\n**Priority:** P2 • **Complexity:** S" \
"testing,P2"

create_issue "Telemetry breadcrumbs for watchlist & telegram" \
"**AC:** Add structured logs for watchlist resolution and telegram sends (event, latency, outcome).\n\n**Priority:** P2 • **Complexity:** S" \
"telemetry,P2"

create_issue "Docs: route registration policy" \
"**AC:** Document router inclusion strategy.\n\n**Priority:** P3 • **Complexity:** S" \
"docs,P3"

create_issue "Streamlit dashboard guardrails" \
"**AC:** Display friendly 'not configured' if DB missing.\n\n**Priority:** P3 • **Complexity:** S" \
"monitoring,P3"

echo "✅ All issues and labels created successfully in $REPO."