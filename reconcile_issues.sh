#!/usr/bin/env zsh
set -euo pipefail

REPO="zsh04/ai_trader"
OWNER="zsh04"
PROJECT_NAME="ai-trader-app"

echo "🔄 Reconciling issues, labels, milestones, and project membership for $REPO …"

# ---------- helpers ----------
milestone_number() { gh api -X GET "repos/$REPO/milestones" -q ".[]|select(.title==\"$1\")|.number" 2>/dev/null || true; }
ensure_milestone() {
  local title="$1" desc="$2" due="${3:-}"
  local num="$(milestone_number "$title")"
  if [[ -z "$num" ]]; then
    if [[ -n "$due" ]]; then
      gh api -X POST "repos/$REPO/milestones" -f title="$title" -f description="$desc" -f due_on="$due" >/dev/null
    else
      gh api -X POST "repos/$REPO/milestones" -f title="$title" -f description="$desc" >/dev/null
    fi
    echo "➕ milestone: $title"
  fi
}

project_number() {
  gh project view "$PROJECT_NAME" --owner "$OWNER" --format json -q '.number' 2>/dev/null || true
}

issue_number_by_title() {
  local title="$1"
  gh issue list --repo "$REPO" --state all --search "in:title \"$title\"" --json number,title -q \
    '.[] | select(.title=="'"$title"'") | .number' 2>/dev/null || true
}

ensure_in_project() {
  local proj_num="$1" issue_num="$2"
  # Add unconditionally; gh will noop if already there.
  gh project item-add "$proj_num" --owner "$OWNER" --url "https://github.com/$REPO/issues/$issue_num" >/dev/null || true
}

upsert_issue() {
  local title="$1" body="$2" labels_csv="$3" milestone_title="$4"

  # Ensure milestone exists
  ensure_milestone "M1 — Critical Hardening" "P0 hardening items"
  ensure_milestone "M2 — Functional Completion" "P1 functional work"
  ensure_milestone "M3 — Observability & Polish" "P2 polish & telemetry"
  ensure_milestone "M4 — Docs & Nice-to-haves" "P3 docs & extras"

  local ms="$milestone_title"
  local n="$(issue_number_by_title "$title")"
  if [[ -n "$n" ]]; then
    # Update labels/body/milestone
    gh issue edit "$n" --repo "$REPO" \
      --add-label "$labels_csv" \
      --milestone "$ms" \
      --body "$body" >/dev/null
    echo "✏️  updated #$n: $title"
  else
    # Create new
    n=$(gh issue create --repo "$REPO" --title "$title" --body "$body" --label "$labels_csv" --milestone "$ms")
    echo "🆕 created #$n: $title"
  fi

  # Ensure membership in project
  local proj_num="$(project_number)"
  if [[ -n "$proj_num" ]]; then
    ensure_in_project "$proj_num" "$n"
  else
    echo "⚠️  project '$PROJECT_NAME' not found under owner '$OWNER' (skipping project add)"
  fi
}

# ---------- delta adds ----------
upsert_issue \
"Decide router aggregation strategy" \
"**Goal:** Pick a single approach: (A) mount central aggregator \`app/api/routes.mount(app)\` or (B) keep explicit per-router includes and deprecate aggregator.\n\n**AC:** Decision documented; code matches; tests assert mounted endpoints.\n\n**Priority:** P2 • **Complexity:** M" \
"api,P2" \
"M3 — Observability & Polish"

upsert_issue \
"Remove or integrate wiring router" \
"**Goal:** Avoid divergence between tests and prod by either removing \`app.wiring.router\` or mounting it consistently.\n\n**AC:** Single source of truth; tests run against same router path as prod.\n\n**Priority:** P2 • **Complexity:** S" \
"api,P2" \
"M3 — Observability & Polish"

upsert_issue \
"Docs: .env auto-loading behavior" \
"**Goal:** Document how \`.env\` is auto-loaded on import, when to disable in containers, and the supported env names.\n\n**AC:** README/AGENTS updated; sample prod env guidance.\n\n**Priority:** P2 • **Complexity:** S" \
"docs,P2" \
"M3 — Observability & Polish"

upsert_issue \
"Consolidate Alpaca feed env names" \
"**Goal:** Use a single env key (e.g. \`ALPACA_FEED\`) for both market health and data client, with alias support for legacy names.\n\n**AC:** One canonical setting; alias path warns; tests updated.\n\n**Priority:** P1 • **Complexity:** S" \
"adapters,P1" \
"M2 — Functional Completion"

upsert_issue \
"Finviz failure logging test" \
"**Goal:** When Finviz module/preset is missing or errors, we warn and fall back.\n\n**AC:** Test asserts warning + safe fallback; CI green.\n\n**Priority:** P3 • **Complexity:** S" \
"tests,P3" \
"M4 — Docs & Nice-to-haves"

upsert_issue \
"Manual watchlist override behavior" \
"**Goal:** Make \`/watchlist manual\` explicit: either return manual list or emit clear guidance if unset.\n\n**AC:** UX clarified; tests verify non-empty or helpful message; no silent empty lists.\n\n**Priority:** P2 • **Complexity:** M" \
"watchlist,P2" \
"M3 — Observability & Polish"

# ---------- updates (change milestone/priority for an existing one) ----------
# Find issue by exact title and adjust labels/milestone if needed
retitle_label_milestone() {
  local title="$1" new_labels="$2" new_milestone="$3" new_body_opt="$4"
  local num="$(issue_number_by_title "$title")"
  if [[ -n "$num" ]]; then
    IFS=',' read -r -A labs <<< "$new_labels"
    for l in "${labs[@]}"; do [[ -n "$l" ]]; done
    gh issue edit "$num" --repo "$REPO" --milestone "$new_milestone" >/dev/null
    # Replace priority label if needed: remove P2, add P1, etc.
    # Fetch existing labels and adjust
    existing=$(gh issue view "$num" --repo "$REPO" --json labels -q '.labels[].name' | tr '\n' ',' | sed 's/,$//')
    # Remove any Px labels before adding the new one
    for p in P0 P1 P2 P3; do gh issue edit "$num" --repo "$REPO" --remove-label "$p" >/dev/null || true; done
    gh issue edit "$num" --repo "$REPO" --add-label "$new_labels" >/dev/null
    if [[ -n "${new_body_opt:-}" ]]; then
      gh issue edit "$num" --repo "$REPO" --body "$new_body_opt" >/dev/null
    fi
    echo "♻️  retagged #$num: $title"
    # add back to project if missing
    local proj_num="$(project_number)"
    [[ -n "$proj_num" ]] && ensure_in_project "$proj_num" "$num"
  else
    echo "⚠️  not found (skipped retag): $title"
  fi
}

retitle_label_milestone \
"Env schema validator" \
"infra,P1" \
"M2 — Functional Completion"

echo "✅ Reconcile complete."