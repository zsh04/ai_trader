from __future__ import annotations

import importlib
import os
from datetime import datetime, timezone

REQUIRED_ENVS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_DEFAULT_CHAT_ID",
    "TELEGRAM_WEBHOOK_SECRET",
    # add DB envs if you require PG in dev:
    # "DATABASE_URL",
]


def check_env():
    missing = [k for k in REQUIRED_ENVS if not os.getenv(k)]
    return missing


def check_imports():
    modules = [
        "app.main",
        "app.providers.alpaca_provider",
        "app.providers.yahoo_provider",
        "app.data.data_client",
        "app.scanners.watchlist_builder",
        "app.adapters.notifiers.telegram",
    ]
    errors = []
    for m in modules:
        try:
            importlib.import_module(m)
        except Exception as e:
            errors.append((m, repr(e)))
    return errors


if __name__ == "__main__":
    print("[sanity] running at", datetime.now(timezone.utc).isoformat())
    missing = check_env()
    if missing:
        print("[sanity] missing env:", ", ".join(missing))
    else:
        print("[sanity] env ok")

    errs = check_imports()
    if errs:
        print("[sanity] import errors:")
        for m, e in errs:
            print("  -", m, "=>", e)
    else:
        print("[sanity] imports ok")
