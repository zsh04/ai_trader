from __future__ import annotations

from statistics import mean
from typing import List, Optional

from app.core.timeutils import now_utc, session_for
from app.data.data_client import batch_latest_ohlcv, get_universe
from app.utils.env import MAX_WATCHLIST

# New: optional external sources
try:
    from app.sources import dedupe_merge  # type: ignore
except Exception:
    def dedupe_merge(*groups, limit: int | None = None):  # fallback no-op
        seen = set()
        out: list[str] = []
        for g in groups:
            for s in (g or []):
                u = str(s).strip().upper()
                if not u or u in seen:
                    continue
                seen.add(u)
                out.append(u)
                if limit and len(out) >= limit:
                    return out
        return out

try:
    from app.sources.finviz_source import fetch_symbols as finviz_fetch  # type: ignore
except Exception:
    def finviz_fetch(*args, **kwargs):  # type: ignore
        return []

# --------------------------------------------------------------------------------------
# Lightweight helpers (kept for future scanner enrichment)
# --------------------------------------------------------------------------------------


def _gap_pct(today_open: float, prev_close: float) -> float:
    if not prev_close or prev_close <= 0:
        return 0.0
    return (today_open - prev_close) / prev_close * 100.0


def _spread_pct(bid: float, ask: float) -> float:
    if not bid or not ask:
        return 999.0
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 999.0
    return (ask - bid) / mid * 100.0


def _pick_price(
    latest_trade: dict | None, daily_bar: dict | None, prev_daily: dict | None
) -> float:
    """Use latestTrade price if present; fallback to today's open or previous close."""
    try:
        if latest_trade and latest_trade.get("p"):
            p = float(latest_trade["p"])  # type: ignore[index]
            if p > 0:
                return p
    except Exception:
        pass
    try:
        if daily_bar and daily_bar.get("o"):
            o = float(daily_bar["o"])  # type: ignore[index]
            if o > 0:
                return o
    except Exception:
        pass
    try:
        if prev_daily and prev_daily.get("c"):
            c = float(prev_daily["c"])  # type: ignore[index]
            if c > 0:
                return c
    except Exception:
        pass
    return 0.0


def _volumes_for_rvol(bars: list[dict], daily_bar: dict | None) -> tuple[float, float]:
    """Return (today_volume, avg_5d_volume). If today's volume is 0 premarket, we still return 0."""
    hist = [b.get("v", 0) for b in (bars or []) if b.get("v")]
    avg5 = float(mean(hist[-5:])) if hist else 0.0
    today = float((daily_bar or {}).get("v") or 0.0)
    return today, avg5


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


def build_watchlist(
    symbols: list[str] | None = None,
    include_filters: bool = True,
    passthrough: bool = False,  # reserved for future use
    include_ohlcv: bool = True,  # kept for compatibility; batch already returns OHLCV
    *,
    # New knobs for external sources
    include_finviz: bool = False,
    finviz_preset: Optional[str] = None,
    finviz_filters: Optional[list[str]] = None,
    limit: Optional[int] = None,
) -> dict:
    """
    Unified watchlist creator:
      - symbols provided => manual mode
      - symbols None/[]  => scanning mode (apply filters if include_filters)
    Session-aware enrichment via batch_latest_ohlcv.

    New:
      - include_finviz/finviz_preset/finviz_filters to pull symbols from Finviz
      - limit to cap merged list (fallback to MAX_WATCHLIST)
    """
    # 1) pick candidate symbols from manual/scanner/sources
    manual = sorted({s.strip().upper() for s in (symbols or []) if s and s.strip()})

    scanner_default = [] if manual else scan_candidates()  # only when no manual symbols

    finviz_list: list[str] = []
    if include_finviz:
        finviz_list = finviz_fetch(
            preset=finviz_preset or "Top Gainers",
            filters=finviz_filters or [],
            max_symbols=100,
        )

    hard_cap = limit if (isinstance(limit, int) and limit > 0) else (
        MAX_WATCHLIST if isinstance(MAX_WATCHLIST, int) and MAX_WATCHLIST > 0 else 15
    )

    candidates = dedupe_merge(manual, scanner_default, finviz_list, limit=hard_cap)

    # 2) optionally apply filters (currently only caps/cleanup)
    if include_filters:
        candidates = apply_filters(candidates)

    # 3) enrich with latest price + OHLCV
    snap = batch_latest_ohlcv(candidates)

    # 4) structure response
    items: list[dict] = []
    for sym in candidates:
        d = snap.get(sym, {"last": 0.0, "price_source": "none", "ohlcv": {}})
        items.append(
            {
                "symbol": sym,
                "last": float(d.get("last", 0.0) or 0.0),
                "price_source": d.get("price_source", "none"),
                "ohlcv": d.get("ohlcv", {}),
            }
        )

    return {
        "session": session_for(now_utc()),
        "asof_utc": now_utc().isoformat(),
        "count": len(items),
        "items": items,
    }


# --------------------------------------------------------------------------------------
# Temporary scanning stubs (replace with real gap/RVOL/spread filters soon)
# --------------------------------------------------------------------------------------


def scan_candidates() -> List[str]:
    """Default scanning universe (placeholder until real scanner is wired)."""
    return get_universe()


def apply_filters(symbols: List[str]) -> List[str]:
    """No-op filter other than capping list length with MAX_WATCHLIST."""
    syms = [s.strip().upper() for s in symbols if s and s.strip()]
    cap = MAX_WATCHLIST if isinstance(MAX_WATCHLIST, int) and MAX_WATCHLIST > 0 else 15
    return syms[:cap]
