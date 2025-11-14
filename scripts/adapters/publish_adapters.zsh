#!/usr/bin/env zsh
set -euo pipefail

# Defaults (override via env or flags)
STG_ACCOUNT=${STG_ACCOUNT:-aitraderblobstore}
ADAPTERS_CONTAINER=${ADAPTERS_CONTAINER:-adapters}
SERVICE_DEFAULT=${SERVICE_DEFAULT:-finbert}   # finbert | chronos2
ADAPTER_TYPE_DEFAULT=${ADAPTER_TYPE_DEFAULT:-peft_lora}
BASE_MODEL_DEFAULT=${BASE_MODEL_DEFAULT:-}     # auto-picked if blank (see below)
ADAPTER_LOCAL_BASES=${ADAPTER_LOCAL_BASES:-"adapters scripts/adapters"}

usage() {
  cat <<EOF
Usage:
  $(basename "$0") -s <service> -t <tag> [ -d <local_adapter_dir> | -r <hf_repo> [-c <hf_rev>] ] [ -L ]

  -s   Service name (finbert | chronos2)
  -t   Adapter tag (e.g., base, 20251114-lora-a)
  -d   Local adapter directory (contains PEFT files, e.g., adapter_config.json, *.safetensors).
       If omitted, this script will auto-discover:
         - adapters/<service>/<tag>
         - scripts/adapters/<service>/<tag>
  -r   Hugging Face repo id for the adapter (e.g., myorg/finbert-peft)
  -c   HF revision/commit (default: main)
  -L   Also write adapters/<service>/latest.json pointer to this tag

Env:
  STG_ACCOUNT            (default: ${STG_ACCOUNT})
  ADAPTERS_CONTAINER     (default: ${ADAPTERS_CONTAINER})
  ADAPTER_TYPE_DEFAULT   (default: ${ADAPTER_TYPE_DEFAULT})
  BASE_MODEL_DEFAULT     (optional explicit base model repo, else auto by service)

Examples:
  # From local dir (repo-local path under scripts/)
  STG_ACCOUNT=aitraderblobstore \\
  scripts/adapters/publish_adapters.zsh -s finbert -t base -d scripts/adapters/finbert/base -L

  # From HF repo + commit
  scripts/adapters/publish_adapters.zsh -s chronos2 -t 20251114-lora-a \\
    -r myorg/chronos2-peft -c 9b3f2d1

  # Auto-discover local dir (no -d) in adapters/<service>/<tag> or scripts/adapters/<service>/<tag>
  scripts/adapters/publish_adapters.zsh -s finbert -t base -L
EOF
  exit 1
}

# --- helpers ---
require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1" >&2; exit 1; }; }
file_size() { stat -f%z "$1" 2>/dev/null || stat -c%s "$1"; }  # macOS or Linux
sha256() { (command -v sha256sum >/dev/null && sha256sum "$1" | awk '{print $1}') || shasum -a 256 "$1" | awk '{print $1}'; }

require_cmd az
require_cmd tar
require_cmd python

# Prefer python3; fall back to python
PYTHON_BIN=${PYTHON_BIN:-$(command -v python3 || command -v python || true)}
[[ -n "${PYTHON_BIN}" ]] || { echo "Missing python3/python" >&2; exit 1; }

SERVICE="$SERVICE_DEFAULT"
TAG=""
SRC_DIR=""
HF_REPO=""
HF_REV="main"
WRITE_LATEST=0

while getopts ":s:t:d:r:c:Lh" opt; do
  case $opt in
    s) SERVICE="$OPTARG" ;;
    t) TAG="$OPTARG" ;;
    d) [[ -d "$OPTARG" ]] || { echo "Adapter directory not found: $OPTARG" >&2; exit 1; }
       SRC_DIR="$(cd "$OPTARG" && pwd)" ;;
    r) HF_REPO="$OPTARG" ;;
    c) HF_REV="$OPTARG" ;;
    L) WRITE_LATEST=1 ;;
    h|*) usage ;;
  esac
done

[[ -z "$SERVICE" || -z "$TAG" ]] && usage
if [[ -n "$SRC_DIR" && -n "$HF_REPO" ]]; then
  echo "Error: use only one of -d or -r." >&2; exit 1
fi

# Auto-pick base model if not provided
if [[ -z "${BASE_MODEL_DEFAULT}" ]]; then
  case "$SERVICE" in
    finbert) BASE_MODEL="ProsusAI/finbert" ;;
    chronos2) BASE_MODEL="amazon/chronos-t5-large" ;;
    *) echo "Unknown service '$SERVICE' – set BASE_MODEL_DEFAULT explicitly." >&2; exit 1 ;;
  esac
else
  BASE_MODEL="$BASE_MODEL_DEFAULT"
fi

TMP_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TMP_ROOT"; }
trap cleanup EXIT

ensure_hf() {
  "$PYTHON_BIN" - <<'PY' 2>/dev/null
import importlib, sys
sys.exit(0 if importlib.util.find_spec("huggingface_hub") else 1)
PY
  if [[ $? -eq 0 ]]; then
    echo "Using system $PYTHON_BIN with huggingface_hub" >&2
    echo "$PYTHON_BIN"
    return 0
  fi
  echo "Creating ephemeral venv with huggingface_hub ..." >&2
  "$PYTHON_BIN" -m venv "$TMP_ROOT/venv" >/dev/null 2>&1 || true
  if [[ -x "$TMP_ROOT/venv/bin/python" ]]; then
    V_PY="$TMP_ROOT/venv/bin/python"
    "$V_PY" -m pip install --upgrade pip >/dev/null
    "$V_PY" -m pip install --quiet huggingface_hub >/dev/null
    echo "$V_PY"
  else
    "$PYTHON_BIN" -m pip install --user --quiet huggingface_hub >/dev/null
    echo "$PYTHON_BIN"
  fi
}

# If HF repo provided, snapshot into temp dir
if [[ -n "$HF_REPO" ]]; then
  echo "Downloading adapter from hf://${HF_REPO}@${HF_REV} ..." >&2
  RUN_PY=$(ensure_hf)
  "$RUN_PY" - "$HF_REPO" "$HF_REV" "$TMP_ROOT" <<'PY'
import sys
from huggingface_hub import snapshot_download
repo, rev, tmp = sys.argv[1], sys.argv[2], sys.argv[3]
dst = snapshot_download(repo_id=repo, revision=rev, local_dir=tmp+"/adapter_src", local_dir_use_symlinks=False)
print(dst)
PY
  SRC_DIR="$TMP_ROOT/adapter_src"
fi

# Auto-discover local adapter directory when -d not provided
if [[ -z "$SRC_DIR" && -z "$HF_REPO" ]]; then
  for base in $=ADAPTER_LOCAL_BASES; do
    cand="$base/$SERVICE/$TAG"
    if [[ -d "$cand" ]]; then
      SRC_DIR="$(cd "$cand" && pwd)"
      break
    fi
  done
  if [[ -z "$SRC_DIR" ]]; then
    echo "Error: could not locate adapter dir. Create one at 'adapters/$SERVICE/$TAG' or 'scripts/adapters/$SERVICE/$TAG', or pass -d <dir>." >&2
    exit 1
  fi
fi

echo "[*] Using adapter source: $SRC_DIR" >&2

# Basic sanity check for PEFT artifacts (zsh-nullglob safe)
{
  setopt local_options null_glob
  typeset -a _sfts
  _sfts=("$SRC_DIR"/*.safetensors(.N))
  if [[ ! -e "$SRC_DIR/adapter_config.json" && ${#_sfts} -eq 0 ]]; then
    echo "Warning: $SRC_DIR does not contain typical PEFT files (adapter_config.json, *.safetensors). Continuing anyway." >&2
  fi
}

# Package
ARCHIVE="$TMP_ROOT/adapter.tar.gz"
tar -C "$SRC_DIR" -czf "$ARCHIVE" .

SHA=$(sha256 "$ARCHIVE")
SIZE=$(file_size "$ARCHIVE")
NOW_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
CREATED_BY="${CREATED_BY:-$(git config user.email 2>/dev/null || whoami)}"
ADAPTER_TYPE="${ADAPTER_TYPE:-$ADAPTER_TYPE_DEFAULT}"

# Metadata
META="$TMP_ROOT/metadata.json"
if [[ -n "$HF_REPO" ]]; then
  SRC_JSON="\"hf_repo\":\"$HF_REPO\",\"hf_revision\":\"$HF_REV\""
else
  SRC_JSON="\"local_dir\":\"$SRC_DIR\""
fi

cat > "$META" <<JSON
{
  "service": "$SERVICE",
  "tag": "$TAG",
  "adapter_type": "$ADAPTER_TYPE",
  "base_model": "$BASE_MODEL",
  "source": { $SRC_JSON },
  "artifact": {
    "filename": "adapter.tar.gz",
    "sha256": "$SHA",
    "size_bytes": $SIZE,
    "content_type": "application/gzip"
  },
  "created_at": "$NOW_UTC",
  "created_by": "$CREATED_BY"
}
JSON

DEST_PREFIX="${SERVICE}/${TAG}"
echo "Uploading to blob://${ADAPTERS_CONTAINER}/${DEST_PREFIX}/ ..." >&2

# Ensure container exists
az storage container create --auth-mode login --account-name "$STG_ACCOUNT" --name "$ADAPTERS_CONTAINER" >/dev/null || true

# Upload artifacts (requires 'az login' and RBAC: Storage Blob Data {Reader|Contributor})
az storage blob upload \
  --account-name "$STG_ACCOUNT" \
  --container-name "$ADAPTERS_CONTAINER" \
  --file "$ARCHIVE" \
  --name "${DEST_PREFIX}/adapter.tar.gz" \
  --content-type "application/gzip" \
  --overwrite true \
  --auth-mode login >/dev/null

az storage blob upload \
  --account-name "$STG_ACCOUNT" \
  --container-name "$ADAPTERS_CONTAINER" \
  --file "$META" \
  --name "${DEST_PREFIX}/metadata.json" \
  --content-type "application/json" \
  --overwrite true \
  --auth-mode login >/dev/null

if [[ $WRITE_LATEST -eq 1 ]]; then
  LATEST="$TMP_ROOT/latest.json"
  cat > "$LATEST" <<JSON
{ "service": "$SERVICE", "current_tag": "$TAG", "updated_at": "$NOW_UTC" }
JSON
  az storage blob upload \
    --account-name "$STG_ACCOUNT" \
    --container-name "$ADAPTERS_CONTAINER" \
    --file "$LATEST" \
    --name "${SERVICE}/latest.json" \
    --content-type "application/json" \
    --overwrite true \
    --auth-mode login >/dev/null
fi

echo "Publish complete:"
echo "  adapters/${SERVICE}/${TAG}/adapter.tar.gz (sha256: $SHA, $SIZE bytes)"
echo "  adapters/${SERVICE}/${TAG}/metadata.json"
[[ $WRITE_LATEST -eq 1 ]] && echo "  adapters/${SERVICE}/latest.json -> $TAG"