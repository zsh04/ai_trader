# Scripts Overview

Convenience scripts that support development, operations, and monitoring. Most
scripts expect to be run from the repository root (paths assume the current
working directory is the repo).

| Script | Description |
|--------|-------------|
| `scripts/dev.sh` | CLI wrapper for common dev tasks: create/refresh `.venv`, install runtime + dev deps, run black/ruff/bandit, and execute pytest. |
| `scripts/build_api.sh` | Build the API Docker image (`Dockerfile`) with optional tag/context arguments. |
| `scripts/build_ui.sh` | Build the UI/Streamlit Docker image (`infra/docker/Dockerfile.ui`) with optional tag/context arguments. |
| `scripts/check_secrets.py` | Validates that local environment variables (or `.env.dev`) include values for each documented Key Vault secret. Returns non-zero if required entries are missing. |
| `scripts/kv_sync_from_env.zsh` | Pushes non-empty variables from an env file to Azure Key Vault secret names defined in the mapping (mirrors `docs/operations/secrets.md`). |
| `scripts/check_alpaca_entitlement.py` | Probes Alpaca market data (IEX/SIP entitlements, snapshots, bars) to confirm credentials and entitlements are functioning. |

> Tip: run `chmod +x` on shell scripts after cloning if the executable bit is
> stripped. Use `./scripts/dev.sh -h` to list available dev commands.
