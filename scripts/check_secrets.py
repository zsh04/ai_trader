#!/usr/bin/env python3
"""
Validate that local environment variables align with the documented Key Vault ↔ env mapping.

Usage:
    python scripts/check_secrets.py            # defaults to .env.dev if present
    python scripts/check_secrets.py --env-file path/to/.env.local

The script merges the current process environment with values parsed from the
optional env file and reports which application settings are missing or empty.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Dict, Iterable, Tuple

KEY_VAULT_TO_ENV: Tuple[Tuple[str, str, bool], ...] = (
    ("ALPACA-KEY-ID", "ALPACA_API_KEY", True),
    ("ALPACA-SECRET-KEY", "ALPACA_API_SECRET", True),
    ("ALPHAVANTAGE-API-KEY", "ALPHAVANTAGE_API_KEY", True),
    ("FINNHUB-API-KEY", "FINNHUB_API_KEY", True),
    ("TWELVEDATA-API-KEY", "TWELVEDATA_API_KEY", False),
    ("AZURE-STORAGE-CONNECTION-STRING", "AZURE_STORAGE_CONNECTION_STRING", False),
    ("AZURE-STORAGE-ACCOUNT-KEY", "AZURE_STORAGE_ACCOUNT_KEY", False),
    ("DATABASE-URL", "DATABASE_URL", True),
    ("PG-PASSWORD", "PGPASSWORD", False),
    ("ADMIN-PASSPHRASE", "ADMIN_PASSPHRASE", False),
    ("GRAFANA-BASIC-AUTH", "GRAFANA_BASIC_AUTH", False),
    ("OTEL-EXPORTER-OTLP-HEADERS", "OTEL_EXPORTER_OTLP_HEADERS", False),
    ("SENTRY-DSN", "SENTRY_DSN", False),
    ("ACR-USERNAME", "ACR_USERNAME", False),
    ("ACR-PASSWORD", "ACR_PASSWORD", False),
)


def parse_env_file(path: Path) -> Dict[str, str]:
    """Parse a simple KEY=VALUE env file."""
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip("'\"")
    return env


def resolve_env(env_file: Path | None) -> Dict[str, str]:
    merged = dict(os.environ)
    if env_file:
        merged.update(parse_env_file(env_file))
    return merged


def find_missing(
    env: Dict[str, str], mapping: Iterable[Tuple[str, str, bool]]
) -> Tuple[Dict[str, str], Dict[str, str]]:
    missing_required: Dict[str, str] = {}
    missing_optional: Dict[str, str] = {}
    for kv_name, env_var, required in mapping:
        value = env.get(env_var)
        if value is None or value == "":
            target = missing_required if required else missing_optional
            target[kv_name] = env_var
    return missing_required, missing_optional


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Key Vault ↔ env mapping coverage."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Optional .env-style file to merge with current environment (defaults to .env.dev if present).",
    )
    args = parser.parse_args()

    env_file = args.env_file
    if env_file is None:
        default_env = Path(".env.dev")
        if default_env.exists():
            env_file = default_env

    merged_env = resolve_env(env_file)
    missing_required, missing_optional = find_missing(merged_env, KEY_VAULT_TO_ENV)

    if env_file:
        print(f"Checked environment using file: {env_file}")
    else:
        print("Checked environment using process variables only.")

    if not missing_required and not missing_optional:
        print("✅ All documented secrets have corresponding environment values.")
        return 0

    if missing_required:
        print("❌ Missing required secrets:")
        for kv_name, env_var in missing_required.items():
            print(f"  - Key Vault secret '{kv_name}' → env var '{env_var}' is unset.")
    if missing_optional:
        print("⚠️ Optional secrets not present (set if relevant):")
        for kv_name, env_var in missing_optional.items():
            print(f"  - {kv_name} → {env_var}")
    print("Update the Key Vault secret or local env file before deploying.")
    return 1 if missing_required else 0


if __name__ == "__main__":  # pragma: no mutate
    raise SystemExit(main())
