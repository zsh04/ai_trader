#!/usr/bin/env python3
"""Quick verification helper for Azure Blob configuration.

Run `python scripts/check_blob_env.py` (or `./scripts/check_blob_env.py` if executable)
from the repo root. The script inspects the commonly used environment variables
and exits with a non-zero status when uploads are likely to fail.
"""

from __future__ import annotations

import os
import sys
from typing import Dict

from app.config import settings


def _has_value(value: str | None) -> bool:
    return bool((value or "").strip())


def summarize_env() -> Dict[str, bool]:
    conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    account = os.getenv("AZURE_STORAGE_ACCOUNT") or settings.blob_account
    key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY") or settings.blob_key
    container = (
        os.getenv("AZURE_STORAGE_CONTAINER_NAME")
        or os.getenv("AZURE_STORAGE_CONTAINER_DATA")
        or settings.blob_container
    )
    return {
        "AZURE_STORAGE_CONNECTION_STRING": _has_value(conn),
        "AZURE_STORAGE_ACCOUNT": _has_value(account),
        "AZURE_STORAGE_ACCOUNT_KEY": _has_value(key),
        "AZURE_STORAGE_CONTAINER_NAME": _has_value(container),
    }


def main() -> None:
    status = summarize_env()
    print("Azure Blob configuration check:\n")
    for key, present in status.items():
        flag = "OK" if present else "MISSING"
        print(f"  - {key}: {flag}")

    if status["AZURE_STORAGE_CONNECTION_STRING"]:
        print("\nConnection string detected; account/key checks are optional.")
        sys.exit(0)

    missing = [
        k
        for k, present in status.items()
        if k != "AZURE_STORAGE_CONNECTION_STRING" and not present
    ]
    if missing:
        print("\nOne or more required values are missing:")
        for key in missing:
            print(f"  * {key}")
        print(
            "\nSet the connection string or supply account/key/container env vars before running backtests."
        )
        sys.exit(1)

    print(
        "\nAccount/key/container detected. Managed identity or service principal auth should succeed."
    )


if __name__ == "__main__":
    main()
