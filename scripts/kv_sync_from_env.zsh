#!/usr/bin/env zsh
# Sync selected entries from a .env file to Azure Key Vault (zsh, no sourcing, with diagnostics).
# usage: ./kv_sync_from_env.zsh <key-vault-name> [env-file=.env]
emulate -L zsh -o pipefail

KV="${1:-${KV:-}}"
ENV_FILE="${2:-.env}"
[[ -z "$KV" ]] && { print -u2 "usage: $0 <key-vault-name> [env-file=.env]"; exit 1; }
[[ -f "$ENV_FILE" ]] || { print -u2 "env file not found: $ENV_FILE"; exit 1; }
command -v az >/dev/null || { print -u2 "Azure CLI (az) not found"; exit 1; }

# ---- mapping: ENV key -> Key Vault secret name (hyphenated) ----
typeset -A MAP; MAP=(
  # Broker / market data
  ALPACA_API_KEY                  ALPACA-KEY-ID
  ALPACA_API_SECRET               ALPACA-SECRET-KEY
  ALPHAVANTAGE_API_KEY            ALPHAVANTAGE-API-KEY
  FINNHUB_API_KEY                 FINNHUB-API-KEY
  TWELVEDATA_API_KEY              TWELVEDATA-API-KEY

  # Storage
  AZURE_STORAGE_CONNECTION_STRING AZURE-STORAGE-CONNECTION-STRING
  AZURE_STORAGE_ACCOUNT_KEY       AZURE-STORAGE-ACCOUNT-KEY

  # Database
  DATABASE_URL                    DATABASE-URL
  PGPASSWORD                      PG-PASSWORD

  # ACR (prefer MI; temporary)
  ACR_USERNAME                    ACR-USERNAME
  ACR_PASSWORD                    ACR-PASSWORD

  # Observability
  GRAFANA_BASIC_AUTH              GRAFANA-BASIC-AUTH
  OTEL_EXPORTER_OTLP_HEADERS      OTEL-EXPORTER-OTLP-HEADERS
  SENTRY_DSN                      SENTRY-DSN

  # App/admin
  ADMIN_PASSPHRASE                ADMIN-PASSPHRASE
)

# ---- parse .env (no expansion), normalize CRLF, strip quotes ----
typeset -A ENVV
while IFS= read -r raw || [[ -n "$raw" ]]; do
  raw="${raw//$'\r'/}"                            # strip CR (Windows line endings)
  line="${raw#"${raw%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "$line" || "$line" == \#* ]] && continue  # skip blanks/comments
  [[ "$line" == export\ * ]] && line="${line#export }"
  [[ "$line" != *"="* ]] && continue

  key="${line%%=*}"; val="${line#*=}"
  key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
  val="${val#"${val%%[![:space:]]*}"}"; val="${val%"${val##*[![:space:]]}"}"

  # strip surrounding quotes
  if [[ "$val" == \"*\" && "$val" == *\" ]]; then
    val="${val#\"}"; val="${val%\"}"
  elif [[ "$val" == \'*\' && "$val" == *\' ]]; then
    val="${val#\'}"; val="${val%\'}"
  fi

  ENVV[$key]="$val"
done < "$ENV_FILE"

# ---- DRY RUN: show what we will push (presence + value length only) ----
print -- "Dry-run (env: $(realpath $ENV_FILE)) — mapped keys present:"
typeset -i present=0 missing=0
for var sec in ${(kv)MAP}; do
  if [[ -n "${ENVV[$var]-}" ]]; then
    printf "  • %-28s → %-30s (len=%d)\n" "$var" "$sec" ${#ENVV[$var]}
    ((present++))
  else
    printf "  • %-28s → %-30s (absent/empty)\n" "$var" "$sec"
    ((missing++))
  fi
done
print -- "--- ${present} present, ${missing} absent. Starting sync…"

# ---- Sync to Key Vault with error capture (continues on failure) ----
typeset -i ok=0 skipped=0 failed=0
for var sec in ${(kv)MAP}; do
  val="${ENVV[$var]-}"
  if [[ -z "$val" ]]; then
    printf "… skip %-28s (empty)\n" "$var"; ((skipped++)); continue
  fi
  # capture stderr to show exact Azure error, suppress stdout
  out="$(az keyvault secret set --only-show-errors -n "$sec" --vault-name "$KV" --value "$val" 2>&1 >/dev/null)"
  if [[ $? -eq 0 ]]; then
    printf "✓ set  %-28s → %-30s\n" "$var" "$sec"; ((ok++))
  else
    printf "✗ fail %-28s → %-30s :: %s\n" "$var" "$sec" "$out"; ((failed++))
  fi
done

echo "---"
echo "done: ${ok} set, ${skipped} skipped, ${failed} failed (vault: ${KV})"
