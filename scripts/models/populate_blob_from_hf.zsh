#!/usr/bin/env zsh
set -euo pipefail

# ----- args -----
# -r repo (e.g., ProsusAI/finbert)
# -s service slug (e.g., finbert)
# -c commit/revision (default: main)
# -a storage account (e.g., aitraderblobstore)
# -C container (default: models)
# -v verbose
REPO=""; SERVICE=""; REV="main"; SA=""; CONT="models"; VERBOSE=0

while getopts "r:s:c:a:C:v" opt; do
  case "$opt" in
    r) REPO="$OPTARG" ;;
    s) SERVICE="$OPTARG" ;;
    c) REV="$OPTARG" ;;
    a) SA="$OPTARG" ;;
    C) CONT="$OPTARG" ;;
    v) VERBOSE=1 ;;
    *) echo "Usage: $0 -r <hf_repo> -s <service> [-c rev] -a <storage_acct> [-C container] [-v]"; exit 2 ;;
  esac
done

[[ -z "$REPO" || -z "$SERVICE" || -z "$SA" ]] && {
  echo "ERROR: -r <repo>, -s <service>, and -a <storage_acct> are required"; exit 2;
}

log() { echo "[$(date -u +%FT%TZ)] $*"; }
[[ $VERBOSE -eq 1 ]] && set -x

# ----- prereqs -----
command -v az >/dev/null || { echo "az CLI not found"; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }

# Ensure we can use AAD for storage
az account show >/dev/null || { echo "Run: az login"; exit 1; }

# Optional: warn if you lack RBAC on the storage account
if ! az role assignment list --scope "$(az storage account show -n "$SA" --query id -o tsv 2>/dev/null)" \
     --assignee "$(az ad signed-in-user show --query id -o tsv 2>/dev/null)" -o tsv 2>/dev/null | grep -qi "Storage Blob Data"; then
  log "WARN: Your principal may lack Storage Blob Data Reader/Contributor on $SA; uploads may fail."
fi

# ----- download from HF -----
TMPDIR="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

log "Downloading snapshot: repo=$REPO rev=$REV -> $TMPDIR"
python3 - <<PY
import os, sys
from pathlib import Path
try:
    from huggingface_hub import snapshot_download
except Exception as e:
    print("ERROR: huggingface_hub not installed. Try: pip install --user huggingface_hub", file=sys.stderr)
    sys.exit(1)

repo = "$REPO"
rev  = "$REV"
dest = Path("$TMPDIR")

# Pull common model assets; include both safetensors and PyTorch .bin
allow = [
    "config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
    "*.txt", "*.model", "*.vocab", "*.merges", "*.spm",
    "*.safetensors", "*.bin"
]
snapshot_dir = snapshot_download(repo_id=repo, revision=rev, allow_patterns=allow)
print(f"SNAPSHOT_DIR={snapshot_dir}")

# Mirror into $TMPDIR preserving structure
import shutil, os
for root, _, files in os.walk(snapshot_dir):
    for f in files:
        src = Path(root)/f
        rel = src.relative_to(snapshot_dir)
        out = dest/rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
print("DOWNLOAD_OK")
PY

log "Download complete. Staging for upload."

# ----- create container if missing -----
log "Ensuring container: sa=$SA cont=$CONT"
az storage container create \
  --account-name "$SA" \
  --name "$CONT" \
  --auth-mode login 1>/dev/null

# ----- upload -----
DEST_PATH="$SERVICE/$REV"
log "Uploading to: https://$SA.blob.core.windows.net/$CONT/$DEST_PATH"
az storage blob upload-batch \
  --auth-mode login \
  --account-name "$SA" \
  -d "$CONT" \
  --destination-path "$DEST_PATH" \
  -s "$TMPDIR" \
  --overwrite true

# small manifest for sanity
MANIFEST="$(mktemp)"
find "$TMPDIR" -type f | sed "s#^$TMPDIR/##" | sort > "$MANIFEST"
az storage blob upload \
  --auth-mode login \
  --account-name "$SA" \
  --container-name "$CONT" \
  --file "$MANIFEST" \
  --name "$DEST_PATH/_manifest.txt" \
  --overwrite true 1>/dev/null

log "Upload complete. Files listed in $DEST_PATH/_manifest.txt"