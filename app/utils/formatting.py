# app/utils/formatting.py
from typing import Dict, List


# app/utils/formatting.py  (small tweak in format_watchlist_telegram)
def format_watchlist_telegram(
    items: List[Dict], title: str, blob_path: str | None = None
) -> str:
    if not items:
        return f"*{title}*\nNo candidates."
    lines = [f"*{title}* — {len(items)} tickers"]
    top = items[:10]
    for it in top:
        sym = it.get("symbol", "?")
        px = it.get("last") or it.get("price") or it.get("c") or 0
        v = it.get("v", 0)
        lines.append(f"`{sym:5}`  ${px:,.2f}  vol {v:,}")
    if blob_path:
        lines.append(f"\n_blob_: `{blob_path}`")
    return "\n".join(lines)


def fmt_money(x) -> str:
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "—"
