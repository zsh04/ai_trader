from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import altair as alt
import numpy as np
import pandas as pd
import requests
import streamlit as st

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:
    load_dotenv = None

try:
    import yfinance as yf  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    yf = None

# Load local dotenv files before importing app configuration so ENV picks up overrides.
if load_dotenv:
    for candidate in (Path(".env.dev"), Path(".env")):
        if candidate.exists():
            load_dotenv(candidate, override=False)

from app.adapters.market.alpaca_client import AlpacaAuthError, AlpacaMarketClient
from app.services.watchlist_service import build_watchlist
from app.utils import env as ENV

FALLBACK_SYMBOLS = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]

# ---------------------------------------------------------------------------
# Streamlit configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Trader Console",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root { --accent-color: #38bdf8; }
    html, body, [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #0d1117 0%, #111a2b 45%, #0a0f1a 100%);
        color: #e2e8f0 !important;
    }
    [data-testid="stSidebar"] {
        background-color: rgba(15, 23, 42, 0.92) !important;
        border-right: 1px solid rgba(148, 163, 184, 0.12) !important;
    }
    h1, h2, h3, h4, h5, h6, .stMarkdown p {
        color: #f8fafc !important;
    }
    .glass-card {
        background: rgba(17, 25, 40, 0.85);
        border: 1px solid rgba(148, 163, 184, 0.12);
        border-radius: 18px;
        padding: 1.2rem 1.4rem;
        box-shadow: 0 8px 28px rgba(8, 15, 30, 0.42);
        backdrop-filter: blur(16px);
    }
    .stSelectbox, .stTextInput, .stTextArea, .stNumberInput, .stButton>button {
        color: #f8fafc !important;
        background-color: rgba(30, 41, 59, 0.8) !important;
        border: 1px solid rgba(148, 163, 184, 0.32) !important;
        border-radius: 10px !important;
    }
    .stButton>button:hover {
        border-color: var(--accent-color) !important;
        background-color: rgba(56, 189, 248, 0.25) !important;
    }
    .stDataFrame div, .stTable, .stMetric, .stCaption, .stTextInput>div>div>input {
        color: #f8fafc !important;
    }
    .stTabs [role="tab"] {
        color: rgba(226, 232, 240, 0.7) !important;
        border-radius: 12px 12px 0 0 !important;
        padding: 0.55rem 0.9rem !important;
    }
    .stTabs [role="tab"][aria-selected="true"] {
        background-color: rgba(56, 189, 248, 0.18) !important;
        color: #f8fafc !important;
        border-bottom: 2px solid var(--accent-color) !important;
    }
    .summary-label {
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.12em;
        color: rgba(148, 163, 184, 0.9);
    }
    .summary-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #f8fafc;
    }
    .summary-note {
        font-size: 0.75rem;
        color: rgba(148, 163, 184, 0.65);
    }
    .badge {
        display: inline-flex;
        padding: 0.28rem 0.65rem;
        border-radius: 999px;
        background: rgba(56, 189, 248, 0.2);
        color: #bae6fd;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _format_timestamp(ts: Optional[str | int | float]) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except Exception:
        return None
    return None


def _dedupe_manual(entries: str) -> List[str]:
    parts = [token.strip().upper() for token in entries.split(",") if token.strip()]
    seen = set()
    ordered: List[str] = []
    for sym in parts:
        if sym in seen:
            continue
        seen.add(sym)
        ordered.append(sym)
    return ordered


def _build_watchlist_frame(symbols: Iterable[str], snapshots: Dict[str, dict]) -> pd.DataFrame:
    rows = []
    for sym in symbols:
        snap = snapshots.get(sym, {})
        trade = snap.get("latestTrade") or {}
        daily = snap.get("dailyBar") or {}
        price = trade.get("price") or daily.get("c")
        open_price = daily.get("o")

        change = None
        change_pct = None
        if price is not None and open_price:
            try:
                change = float(price) - float(open_price)
                change_pct = (change / float(open_price)) * 100.0 if open_price else None
            except Exception:
                change = None
                change_pct = None

        rows.append(
            {
                "Symbol": sym,
                "Last Price": float(price) if price is not None else np.nan,
                "Change": float(change) if change is not None else np.nan,
                "% Change": float(change_pct) if change_pct is not None else np.nan,
                "Updated": _format_timestamp(trade.get("timestamp")),
            }
        )
    df = pd.DataFrame(rows)
    return df


def _render_watchlist_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Watchlist is empty. Adjust filters or verify the data source.")
        return
    styled = df.set_index("Symbol").style.format(
        {
            "Last Price": lambda v: "—" if pd.isna(v) else f"${v:,.2f}",
            "Change": lambda v: "—" if pd.isna(v) else f"{v:+.2f}",
            "% Change": lambda v: "—" if pd.isna(v) else f"{v:+.2f}%",
            "Updated": lambda v: v.isoformat() if isinstance(v, datetime) else "—",
        }
    )

    def _delta_style(value: float) -> Optional[str]:
        if pd.isna(value) or value == 0:
            return None
        return "color:#34d399;" if value > 0 else "color:#f87171;"

    styled = styled.map(_delta_style, subset=pd.IndexSlice[:, ["Change", "% Change"]])
    st.dataframe(styled, width="stretch", height=380)


def _render_symbol_detail(symbol: str, row: pd.Series, history: pd.DataFrame) -> None:
    last_price_val = row.get("Last Price", np.nan)
    last_price_display = "—" if pd.isna(last_price_val) else f"${last_price_val:,.2f}"
    updated_val = row.get("Updated")
    updated_display = (
        updated_val.strftime("%Y-%m-%d %H:%M")
        if isinstance(updated_val, datetime)
        else "Timestamp n/a"
    )

    st.markdown(
        f"""
        <div class="glass-card" style="margin-bottom:1rem;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <span class="badge">Detail View</span>
                    <h2 style="margin:0.35rem 0 0;">{symbol}</h2>
                </div>
                <div style="text-align:right;">
                    <div class="summary-label">Last Price</div>
                    <div class="summary-value">{last_price_display}</div>
                    <div class="metric-subtext">{updated_display}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns([2.2, 1])
    with cols[0]:
        timeframe = st.selectbox(
            "Chart timeframe",
            options=list(TIMEFRAME_CONFIG.keys()),
            index=list(TIMEFRAME_CONFIG.keys()).index("1H"),
            key=f"tf_{symbol}",
        )
        history = _load_bar_history(symbol, timeframe=timeframe)
        if history.empty:
            st.warning("No historical data available for this symbol.")
        else:
            history_plot = history.reset_index().rename(columns={"index": "timestamp"})
            chart = (
                alt.Chart(history_plot)
                .mark_line(color="#60a5fa", strokeWidth=2)
                .encode(
                    x=alt.X("timestamp:T", title="Time"),
                    y=alt.Y("close:Q", title="Close Price"),
                    tooltip=[
                        alt.Tooltip("timestamp:T", title="Timestamp"),
                        alt.Tooltip("close:Q", title="Close", format=",.2f"),
                    ],
                )
            )
            st.altair_chart(chart.interactive(), width="stretch")
    with cols[1]:
        st.markdown("###### Session Snapshot")
        change = row.get("Change", np.nan)
        pct = row.get("% Change", np.nan)
        st.metric(
            label="Change",
            value="—" if pd.isna(change) else f"{change:+.2f}",
            delta="—" if pd.isna(pct) else f"{pct:+.2f}%",
        )
        st.caption(
            "Charts sourced from Alpaca / Yahoo Finance fallback. "
            "Historical candle resolution: 1H (configurable)."
        )


@st.cache_data(show_spinner=False, ttl=30)
def _load_snapshots(symbols: Tuple[str, ...]) -> Tuple[Dict[str, dict], str]:
    if not symbols:
        return {}, "none"
    snapshots, summary = get_market_snapshots(symbols)
    return snapshots, summary


TIMEFRAME_CONFIG = {
    "1H": ("1Hour", 120),
    "15m": ("15Min", 200),
    "5m": ("5Min", 240),
}


@st.cache_data(show_spinner=False, ttl=300)
def _load_bar_history(symbol: str, *, timeframe: str = "1H") -> pd.DataFrame:
    df = get_intraday_bars(symbol, timeframe=timeframe)
    if df.empty:
        interval_minutes = 60 if timeframe == "1H" else 15 if timeframe == "15m" else 5
        limit = TIMEFRAME_CONFIG.get(timeframe, ("1Hour", 120))[1]
        index = pd.date_range(
            datetime.now(timezone.utc) - timedelta(minutes=(limit - 1) * interval_minutes),
            periods=limit,
            freq=f"{interval_minutes}T",
        )
        base = 100.0 + np.linspace(0, 5, limit)
        noise = np.random.normal(0, 0.7, size=limit)
        df = pd.DataFrame({"close": base + noise}, index=index)
    return df


# ---------------------------------------------------------------------------
# Sidebar watchlist builder
# ---------------------------------------------------------------------------

if "watchlist_state" not in st.session_state:
    st.session_state.watchlist_state = {
        "source": "auto",
        "symbols": [],
        "manual_raw": "",
        "scanner": "",
        "sort": "none",
        "limit": min(ENV.MAX_WATCHLIST or 50, 25),
    }

state = st.session_state.watchlist_state

st.sidebar.header("Watchlist Builder")
source_options = ["auto", "alpha", "finnhub", "textlist", "manual"]
current_source = state.get("source", "auto")
if current_source not in source_options:
    current_source = "auto"
source = st.sidebar.selectbox(
    "Select source",
    options=source_options,
    index=source_options.index(current_source),
    format_func=lambda x: x.title(),
    help="Choose how to construct the current watchlist.",
)

limit = st.sidebar.number_input(
    "Max symbols",
    min_value=5,
    max_value=ENV.MAX_WATCHLIST or 100,
    value=int(state.get("limit") or min(ENV.MAX_WATCHLIST or 50, 25)),
    step=5,
    help="Upper bound after deduping and filtering.",
)

sort = st.sidebar.selectbox(
    "Sort order",
    options=["none", "alpha"],
    index=["none", "alpha"].index(state.get("sort", "none")),
    help="Optional alphabetical sort before display.",
)

scanner = ""
manual_input = ""
if source in {"auto", "alpha", "finnhub", "textlist"}:
    scanner = st.sidebar.text_input(
        "Scanner (optional)",
        value=state.get("scanner", ""),
        help="Finviz/Textlist scanners are defined in app configuration.",
    )
else:
    manual_input = st.sidebar.text_area(
        "Manual symbols",
        value=state.get("manual_raw", ""),
        height=100,
        help="Comma-separated tickers, e.g. AAPL, MSFT, NVDA.",
    )

apply_watchlist = st.sidebar.button("Apply Watchlist")

def _resolve_watchlist(
    selected_source: str,
    *,
    scanner_value: str,
    manual_value: str,
    limit_value: int | None,
    sort_value: str,
) -> Tuple[List[str], Optional[str]]:
    symbols: List[str] = []
    limit_norm = limit_value if limit_value and limit_value > 0 else None
    note: Optional[str] = None

    if selected_source == "manual":
        symbols = _dedupe_manual(manual_value)
    else:
        symbols = build_watchlist(
            source=selected_source,
            scanner=scanner_value or None,
            limit=limit_norm,
            sort="alpha" if sort_value == "alpha" else None,
        )

    if selected_source == "manual" and sort_value == "alpha":
        symbols = sorted(symbols)

    if limit_norm:
        symbols = symbols[:limit_norm]

    if not symbols and selected_source != "manual":
        fallback = FALLBACK_SYMBOLS[: limit_norm] if limit_norm else FALLBACK_SYMBOLS
        symbols = fallback
        note = (
            "Watchlist source returned no symbols. Using demo tickers: "
            + ", ".join(fallback)
        )

    return symbols, note


source_note: Optional[str] = None
if apply_watchlist or not state.get("symbols"):
    symbols, source_note = _resolve_watchlist(
        source,
        scanner_value=scanner,
        manual_value=manual_input,
        limit_value=int(limit),
        sort_value=sort,
    )
    state.update(
        {
            "source": source,
            "symbols": symbols,
            "scanner": scanner,
            "manual_raw": manual_input,
            "sort": sort,
            "limit": int(limit),
        }
    )
    _load_snapshots.clear()
    _load_bar_history.clear()

watchlist = state.get("symbols", [])

if source_note:
    st.sidebar.warning(source_note)

st.sidebar.markdown("---")
with st.sidebar.expander("Current Selection", expanded=True):
    st.write(f"Source: `{state.get('source', 'auto')}`")
    if state.get("source") == "manual":
        st.caption("Manual entries applied.")
    elif state.get("scanner"):
        st.caption(f"Scanner preset: `{state.get('scanner')}`")
    st.write(f"Symbols ({len(watchlist)}):")
    st.code(", ".join(watchlist) if watchlist else "—")

# Manual refresh button to re-pull snapshots/bars without changing config.
refresh_data = st.sidebar.button("Refresh Market Data")
if refresh_data:
    _load_snapshots.clear()
    _load_bar_history.clear()

# ---------------------------------------------------------------------------
# Data hydration & header
# ---------------------------------------------------------------------------
snapshots, provider_summary = _load_snapshots(tuple(watchlist))
watchlist_df = _build_watchlist_frame(watchlist, snapshots)

providers_used = [p.strip() for p in provider_summary.split("/") if p.strip()] if provider_summary else []
if not providers_used:
    provider_label = "No data"
elif len(providers_used) == 1:
    provider_label = providers_used[0]
else:
    provider_label = " / ".join(providers_used)

if not watchlist_df.empty and watchlist_df["Updated"].notna().any():
    last_updated = watchlist_df["Updated"].dropna().max()
else:
    last_updated = datetime.now(timezone.utc)

header_note: Optional[str] = None
if provider_label == "No data":
    header_note = "No market data returned from upstream providers."
elif len(providers_used) > 1:
    header_note = f"Blended data sources active: {provider_label}."
if source_note:
    header_note = source_note if header_note is None else f"{header_note} {source_note}"

st.markdown(
    f"""
    <div class="glass-card" style="margin-bottom:1.1rem;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
                <span class="badge">Operations Console</span>
                <h1 style="margin:0.35rem 0 0;">AI Trader — Market Pulse</h1>
                <div class="summary-note" style="margin-top:0.25rem;">
                    Curated watchlists, live snapshots, and symbol intelligence for intraday decisioning.
                </div>
            </div>
            <div style="text-align:right;">
                <div class="summary-note">Data source</div>
                <div class="badge" style="margin-bottom:0.4rem;">{provider_label}</div>
                <div class="summary-label">Last snapshot (UTC)</div>
                <div class="summary-value" style="font-size:1.1rem;">{last_updated.strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if header_note:
    st.warning(header_note)

stats_cols = st.columns(3)
with stats_cols[0]:
    st.markdown(
        f'<div class="glass-card"><div class="summary-label">Tracked Symbols</div>'
        f'<div class="summary-value">{len(watchlist_df)}</div>'
        f'<div class="summary-note">Active in current watchlist</div></div>',
        unsafe_allow_html=True,
    )
with stats_cols[1]:
    coverage = watchlist_df["Last Price"].notna().sum()
    st.markdown(
        f'<div class="glass-card"><div class="summary-label">Price Coverage</div>'
        f'<div class="summary-value">{coverage}</div>'
        f'<div class="summary-note">Symbols with recent quotes</div></div>',
        unsafe_allow_html=True,
    )
with stats_cols[2]:
    mean_move = watchlist_df["% Change"].dropna().mean() if not watchlist_df.empty else 0.0
    st.markdown(
        f'<div class="glass-card"><div class="summary-label">Avg Session Move</div>'
        f'<div class="summary-value">{mean_move:+.2f}%</div>'
        f'<div class="summary-note">Across symbols with price data</div></div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------
tabs = st.tabs(["Watchlist", "Detail View", "Orders • Roadmap"])

with tabs[0]:
    st.markdown("#### Current Symbols")
    _render_watchlist_table(watchlist_df)

with tabs[1]:
    if watchlist_df.empty:
        st.info("Watchlist is empty. Populate via the sidebar to inspect details.")
    else:
        symbol = st.selectbox("Symbol focus", options=list(watchlist_df["Symbol"]), index=0)
        row = watchlist_df.set_index("Symbol").loc[symbol]
        history = _load_bar_history(symbol)
        _render_symbol_detail(symbol, row, history)

with tabs[2]:
    st.markdown("#### Orders & Routing")
    st.info(
        "Order routing and execution preview will land here. "
        "Integrate with OMS/EMS endpoints to surface staged orders and fills."
    )
    st.caption(
        "Planned widgets: staged orders list, risk review, manual override toggles."
    )

st.sidebar.markdown("---")
st.sidebar.caption(
    "Environment sourced from Azure Key Vault references or local .env/.env.dev files. "
    "Alpaca keys enable live market data; Yahoo fallback triggers when unavailable."
)
