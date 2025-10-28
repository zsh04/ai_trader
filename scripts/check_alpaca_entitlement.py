# scripts/check_alpaca_entitlement.py
import datetime as dt
import json
import os
import sys

import requests

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
BASE = "https://data.alpaca.markets/v2"
HEADERS = {"APCA-API-KEY-ID": API_KEY or "", "APCA-API-SECRET-KEY": API_SECRET or ""}

SYMS = ["AAPL", "MSFT", "SPY"]  # fast sanity set
NOW = dt.datetime.utcnow()
START_MIN = (NOW - dt.timedelta(hours=6)).isoformat(timespec="seconds") + "Z"
START_DAY = (NOW - dt.timedelta(days=5)).date().isoformat()


def _req(path, params=None):
    r = requests.get(f"{BASE}{path}", headers=HEADERS, params=params or {}, timeout=20)
    return r.status_code, r.headers, r.text


def check_entitlements():
    ent = {"iex": False, "sip": False, "error": None}
    # Probe IEX and SIP via /stocks/trades (1 record)
    for feed in ("iex", "sip"):
        code, _, body = _req(
            "/stocks/trades", {"symbol": "AAPL", "limit": 1, "feed": feed}
        )
        if code == 200:
            ent[feed] = True
        elif code in (401, 403, 402):
            ent[feed] = False
        else:
            ent["error"] = f"{feed} probe unexpected status {code}: {body[:160]}"
    return ent


def check_snapshots():
    code, _, body = _req("/stocks/snapshots", {"symbols": ",".join(SYMS)})
    if code != 200:
        return False, f"snapshots HTTP {code}: {body[:160]}"
    try:
        j = json.loads(body)
        snaps = j.get("snapshots") or {}
        empty = [s for s in SYMS if not snaps.get(s)]
        if empty:
            return False, f"empty snapshots for: {','.join(empty)}"
        return True, "snapshots OK"
    except Exception as e:
        return False, f"snapshots parse error: {e}"


def check_bars():
    # Minute bars (recent window)
    code, _, body = _req(
        "/stocks/bars",
        {
            "symbols": ",".join(SYMS),
            "timeframe": "1Min",
            "limit": 1,
            "start": START_MIN,
            "feed": "iex",  # be explicit; 'iex' works on free & paid
        },
    )
    if code != 200:
        return False, f"1Min bars HTTP {code}: {body[:160]}"
    try:
        j = json.loads(body)
        bars = j.get("bars") or {}
        miss = [s for s in SYMS if not bars.get(s)]
        if miss:
            return False, f"empty 1Min bars for: {','.join(miss)}"
    except Exception as e:
        return False, f"1Min bars parse error: {e}"

    # Daily bars (avoid “no bar yet” by using past days)
    code, _, body = _req(
        "/stocks/bars",
        {
            "symbols": ",".join(SYMS),
            "timeframe": "1Day",
            "start": START_DAY,
            "limit": 1,
            "feed": "iex",
        },
    )
    if code != 200:
        return False, f"1Day bars HTTP {code}: {body[:160]}"
    try:
        j = json.loads(body)
        bars = j.get("bars") or {}
        miss = [s for s in SYMS if not bars.get(s)]
        if miss:
            return False, f"empty 1Day bars for: {','.join(miss)}"
        return True, "bars OK"
    except Exception as e:
        return False, f"1Day bars parse error: {e}"


def main():
    problems = []

    # Hard fail if creds missing
    if not API_KEY or not API_SECRET:
        print(
            "ALERT: Alpaca API credentials not set (APCA_API_KEY_ID / APCA_API_SECRET_KEY)."
        )
        sys.exit(2)

    ent = check_entitlements()
    if ent.get("error"):
        problems.append(f"entitlement check error: {ent['error']}")
    print(f"Entitlements -> IEX: {ent['iex']} | SIP: {ent['sip']}")

    # Snapshots
    ok, msg = check_snapshots()
    if not ok:
        problems.append(f"snapshots: {msg}")
    print(("OK: " if ok else "ALERT: ") + msg)

    # Bars
    ok, msg = check_bars()
    if not ok:
        problems.append(f"bars: {msg}")
    print(("OK: " if ok else "ALERT: ") + msg)

    # Final status & exit code
    if problems:
        print("FAILURE SUMMARY:")
        for p in problems:
            print(f" - {p}")
        sys.exit(1)
    print("SUCCESS: Alpaca market data looks healthy.")
    sys.exit(0)


if __name__ == "__main__":
    main()
