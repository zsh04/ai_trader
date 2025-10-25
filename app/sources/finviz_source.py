# app/sources/finviz_source.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
import logging

try:
    from finvizfinance.screener import Screener
    _FINVIZ_OK = True
except Exception:
    _FINVIZ_OK = False

log = logging.getLogger(__name__)

# Example presets: “Top Gainers”, “Unusual Volume”, “Most Active”, etc.
# You can also pass advanced filters like: ["sh_avgvol_o3000", "ta_perf_4w20o"]
def fetch_symbols(
    preset: str = "Top Gainers",
    filters: Optional[List[str]] = None,
    max_symbols: int = 50,
) -> List[str]:
    if not _FINVIZ_OK:
        log.warning("finvizfinance not installed; returning []")
        return []
    try:
        s = Screener(filters=filters or [], tickers=[], order="price")
        if preset:
            s.set_filter(signal=preset)  # Finviz “Signal” selector
        df = s.get_screen_df()
        # ‘Ticker’ column is typical; guard for schema drift
        symbols = [str(t).upper() for t in (df.get("Ticker") or []) if str(t).isalpha()]
        # basic sanity: drop weird/OTC forms
        symbols = [s for s in symbols if 1 <= len(s) <= 5]
        return symbols[:max_symbols]
    except Exception as e:
        log.exception("finviz fetch failed: %s", e)
        return []