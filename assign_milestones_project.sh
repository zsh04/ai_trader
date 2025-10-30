#!/usr/bin/env zsh
set -euo pipefail

REPO="zsh04/ai_trader"
# Set to 1 to also add issues to your project board
ADD_TO_PROJECT=0
PROJECT_NAME="ai-trader-app"
OWNER="zsh04"   # org or user that owns the project

echo "🏁 Milestone setup for $REPO"

# --- Helpers ---
have_label() { gh label list --repo "$REPO" --json name -q '.[]|.name' | grep -qx "$1"; }
have_milestone() { gh api -X GET "repos/$REPO/milestones" -q ".[]|select(.title==\"$1\")|.number" 2>/dev/null || true; }
create_milestone() {
  local title="$1" desc="$2" due="${3:-}"
  if [[ -n "$(have_milestone "$title")" ]]; then
    echo "✔️  Milestone exists: $title"
  else
    if [[ -n "$due" ]]; then
      gh api -X POST "repos/$REPO/milestones" -f title="$title" -f description="$desc" -f due_on="$due" >/dev/null
    else
      gh api -X POST "repos/$REPO/milestones" -f title="$title" -f description="$desc" >/dev/null
    fi
    echo "➕ Created milestone: $title"
  fi
}

assign_issues() {
  local label="$1" milestone_title="$2"
  local ms_num
  ms_num=$(have_milestone "$milestone_title")
  if [[ -z "$ms_num" ]]; then
    echo "❌ Missing milestone: $milestone_title"; exit 1
  fi

  echo "🔗 Assigning label '$label' issues to milestone '$milestone_title'…"
  local issues
  issues=($(gh issue list --repo "$REPO" --label "$label" --state open --json number -q '.[].number'))
  if (( ${#issues[@]} == 0 )); then
    echo "  (no open issues with $label)"
  else
    for n in "${issues[@]}"; do
      gh issue edit "$n" --repo "$REPO" --milestone "$milestone_title" >/dev/null
      echo "  #$n → $milestone_title"
    done
  fi
}

# --- Compute due dates (ISO 8601 UTC) ---
iso_date() {
  # macOS vs GNU date
  if date -v +7d +"%Y" >/dev/null 2>&1; then
    case "$1" in
      +7d)  date -u -v+7d  +"%Y-%m-%dT%H:%M:%SZ" ;;
      +21d) date -u -v+21d +"%Y-%m-%dT%H:%M:%SZ" ;;
      +35d) date -u -v+35d +"%Y-%m-%dT%H:%M:%SZ" ;;
      +60d) date -u -v+60d +"%Y-%m-%dT%H:%M:%SZ" ;;
    esac
  else
    case "$1" in
      +7d)  date -u -d "+7 days"  +"%Y-%m-%dT%H:%M:%SZ" ;;
      +21d) date -u -d "+21 days" +"%Y-%m-%dT%H:%M:%SZ" ;;
      +35d) date -u -d "+35 days" +"%Y-%m-%dT%H:%M:%SZ" ;;
      +60d) date -u -d "+60 days" +"%Y-%m-%dT%H:%M:%SZ" ;;
    esac
  fi
}

# --- Create milestones ---
create_milestone "M1 — Critical Hardening" \
  "P0 items: watchlist imports align, /watchlist symbols non-empty across sources, prod webhook auth." \
  "$(iso_date +7d)"

create_milestone "M2 — Functional Completion" \
  "P1 items: CI container boot smoke, legacy watchlist dedupe, polish Telegram routes." \
  "$(iso_date +21d)"

create_milestone "M3 — Observability & Polish" \
  "P2 items: env schema validator, 429 backoff tests, router matrix tests, telemetry breadcrumbs." \
  "$(iso_date +35d)"

create_milestone "M4 — Docs & Nice-to-haves" \
  "P3 items: docs for router policy, Streamlit guardrails, misc cleanup." \
  "$(iso_date +60d)"

# --- Assign issues by label → milestone mapping ---
assign_issues "P0" "M1 — Critical Hardening"
assign_issues "P1" "M2 — Functional Completion"
assign_issues "P2" "M3 — Observability & Polish"
assign_issues "P3" "M4 — Docs & Nice-to-haves"

# --- (Optional) Add to project by name ---
if [[ "$ADD_TO_PROJECT" == "1" ]]; then
  echo "🗂  Adding issues to project: $PROJECT_NAME"
  # Find project number (classic) or node_id (Projects (Beta))
  proj_json=$(gh project view "$PROJECT_NAME" --owner "$OWNER" --format json 2>/dev/null || true)
  if [[ -z "$proj_json" ]]; then
    echo "❌ Could not find project '$PROJECT_NAME' under owner '$OWNER'"; exit 1
  fi
  proj_number=$(echo "$proj_json" | jq -r '.number // empty')
  if [[ -z "$proj_number" ]]; then
    echo "❌ Unable to determine project number"; exit 1
  fi

  # Add all open issues without project membership
  mapfile -t all_issues < <(gh issue list --repo "$REPO" --state open --json number -q '.[].number')
  for n in "${all_issues[@]}"; do
    # gh project item-add works with --owner/--repo + number
    gh project item-add "$proj_number" --owner "$OWNER" --url "https://github.com/$REPO/issues/$n" >/dev/null || true
    echo "  #$n added to project $PROJECT_NAME"
  done
fi

echo "✅ Milestones created and issues assigned."