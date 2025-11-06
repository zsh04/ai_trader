from __future__ import annotations

from statistics import mean
from typing import Iterable, List, Optional

from loguru import logger

from app.core.timeutils import now_utc, session_for
from app.data.data_client import batch_latest_ohlcv, get_universe
from app.services.watchlist_sources import (
    fetch_alpha_vantage_symbols,
    fetch_finnhub_symbols,
    fetch_twelvedata_symbols,
)
from app.utils.env import MAX_WATCHLIST

FALLBACK_WATCHLIST_CAP = 15
INVALID_SPREAD_PCT = 999.0
PCT_SCALE = 100.0
RVOL_LOOKBACK_DAYS = 5
EXTERNAL_MAX_SYMBOLS = 100

# Default cap helper (honors env and safe fallback)
DEFAULT_CAP = (
    MAX_WATCHLIST
    if isinstance(MAX_WATCHLIST, int) and MAX_WATCHLIST > 0
    else FALLBACK_WATCHLIST_CAP
)


def _cap_list(syms: list[str], n: int | None) -> list[str]:
    """Return symbols truncated to desired size (falls back to DEFAULT_CAP)."""
    if not syms:
        return []
    if n is None or n <= 0:
        return syms[:DEFAULT_CAP]
    return syms[:n]


# New: optional external sources
try:
    from app.sources import dedupe_merge  # type: ignore
except Exception:

    def dedupe_merge(*groups: Iterable[str], limit: int | None = None) -> list[str]:
        """Fallback dedupe helper when app.sources is unavailable."""
        seen: set[str] = set()
        out: list[str] = []
        for g in groups:
            for s in g or []:
                u = str(s).strip().upper()
                if not u or u in seen:
                    continue
                seen.add(u)
                out.append(u)
                if limit and len(out) >= limit:
                    return out
        return out


# --------------------------------------------------------------------------------------
# Lightweight helpers (kept for future scanner enrichment)
# --------------------------------------------------------------------------------------


def _gap_pct(today_open: float, prev_close: float) -> float:
    """Compute gap percentage between today's open and prior close."""
    if not prev_close or prev_close <= 0:
        return 0.0
    return (today_open - prev_close) / prev_close * PCT_SCALE


def _spread_pct(bid: float, ask: float) -> float:
    """Return bid/ask spread as a percentage of the midpoint."""
    if not bid or not ask:
        return INVALID_SPREAD_PCT
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return INVALID_SPREAD_PCT
    return (ask - bid) / mid * PCT_SCALE


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
    avg5 = float(mean(hist[-RVOL_LOOKBACK_DAYS:])) if hist else 0.0
    today = float((daily_bar or {}).get("v") or 0.0)
    return today, avg5  # kept for future rVOL features


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


def build_watchlist(
    symbols: list[str] | None = None,
    include_filters: bool = True,
    passthrough: bool = False,  # reserved for future use
    include_ohlcv: bool = True,  # kept for compatibility; batch already returns OHLCV
    *,
    include_external: bool = False,
    external_preset: Optional[str] = None,
    external_filters: Optional[list[str]] = None,
    limit: Optional[int] = None,
) -> dict:
    """
    Build a watchlist payload enriched with latest price/OHLCV data.

    Symbols gathered from manual input, scanner defaults, and optional Finviz
    presets are merged case-insensitively, sorted alphabetically for stability,
    and truncated according to the requested limit before enrichment.
    """
    # capture a single timestamp for consistency
    _ts = now_utc()
    _session = session_for(_ts)

    # decide hard cap early
    hard_cap = limit if (isinstance(limit, int) and limit > 0) else DEFAULT_CAP

    # 1) pick candidate symbols from manual/scanner/sources
    manual = sorted({s.strip().upper() for s in (symbols or []) if s and s.strip()})

    scanner_default = [] if manual else scan_candidates()  # only when no manual symbols

    external_list: list[str] = []
    if include_external:
        try:
            external_list.extend(
                fetch_alpha_vantage_symbols(
                    scanner=external_preset, limit=EXTERNAL_MAX_SYMBOLS
                )
            )
        except Exception as exc:
            logger.warning("alpha vantage watchlist fetch failed: {}", exc)
        if len(external_list) < EXTERNAL_MAX_SYMBOLS:
            try:
                external_list.extend(
                    fetch_finnhub_symbols(
                        scanner=external_preset, limit=EXTERNAL_MAX_SYMBOLS
                    )
                )
            except Exception as exc:
                logger.warning("finnhub watchlist fetch failed: {}", exc)
        if len(external_list) < EXTERNAL_MAX_SYMBOLS:
            try:
                external_list.extend(
                    fetch_twelvedata_symbols(
                        scanner=external_preset, limit=EXTERNAL_MAX_SYMBOLS
                    )
                )
            except Exception as exc:
                logger.warning("twelve data watchlist fetch failed: {}", exc)

    logger.debug(
        (
            "watchlist sources: manual={} scanner={} external={} "
            "include_filters={} limit={}"
        ),
        len(manual),
        len(scanner_default),
        len(external_list),
        include_filters,
        hard_cap,
    )

    # Merge inputs, dedupe case-insensitively (uppercased), then sort for stability.
    candidates = dedupe_merge(manual, scanner_default, external_list)
    candidates = sorted(candidates)
    candidates = _cap_list(candidates, hard_cap)

    if not candidates:
        logger.info("watchlist: no candidates after merge; returning empty payload")
        return {
            "session": _session,
            "asof_utc": _ts.isoformat(),
            "count": 0,
            "items": [],
        }

    # 2) optionally apply filters (currently only caps/cleanup)
    if include_filters:
        candidates = apply_filters(candidates, limit=hard_cap)

    logger.debug("watchlist candidates (post-filters): {}", len(candidates))

    # 3) enrich with latest price + OHLCV
    snap = batch_latest_ohlcv(candidates)

    if not isinstance(snap, dict):
        logger.warning("batch_latest_ohlcv returned non-dict type: {}", type(snap))
        snap = {}

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

    logger.info("watchlist built: {} items", len(items))

    # stable ordering
    items.sort(key=lambda x: x.get("symbol", ""))

    return {
        "session": _session,
        "asof_utc": _ts.isoformat(),
        "count": len(items),
        "items": items,
    }


# --------------------------------------------------------------------------------------
# Temporary scanning stubs (replace with real gap/RVOL/spread filters soon)
# --------------------------------------------------------------------------------------


def scan_candidates() -> List[str]:
    """Default scanning universe (placeholder until real scanner is wired)."""
    return get_universe()


def apply_filters(symbols: List[str], limit: Optional[int] = None) -> List[str]:
    """Primary filter pass (currently enforces uppercase + cap)."""
    syms = [s.strip().upper() for s in symbols if s and s.strip()]
    cap = limit if isinstance(limit, int) and limit > 0 else DEFAULT_CAP
    return _cap_list(syms, cap)
