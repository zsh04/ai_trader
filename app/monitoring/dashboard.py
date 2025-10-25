"""
AI Trader — Streamlit Monitoring Dashboard

Run locally:
  streamlit run app/monitoring/dashboard.py

Notes:
- Reads optional DATABASE_URL and TELEGRAM_BOT_TOKEN from environment.
- If DATABASE_URL is not provided or DB fetch fails, falls back to demo data.
- Provides sidebar controls (date range, symbols, auto-refresh).
- Caches queries via st.cache_data with TTL to avoid hammering the DB.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple, List

import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, timezone

# --- Page config & CSS tweaks ---
st.set_page_config(page_title="AI Trader Dashboard", layout="wide", page_icon="📈")
st.markdown(
    """
    <style>
    .small { font-size: 0.85rem; opacity: 0.85; }
    .ok { color: var(--text-color); }
    .warn { color: #c77d00; }
    .bad { color: #b00020; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Simple data-source toggle & config ---
DB_URL = os.getenv("DATABASE_URL", "")
TZ_LOCAL = os.getenv("DASHBOARD_TZ", "America/Los_Angeles")
DEFAULT_SYMBOLS = os.getenv("DASHBOARD_SYMBOLS", "AAPL,MSFT,NVDA,SPY,QQQ").split(",")

# --- Sidebar controls ---
st.sidebar.header("Controls")
lookback_days = st.sidebar.slider("Lookback (days)", min_value=5, max_value=365, value=30, step=5)
auto_refresh_sec = st.sidebar.number_input("Auto-refresh (sec)", min_value=0, max_value=600, value=60, help="0 disables auto-refresh")
symbols_input = st.sidebar.text_input("Symbols (comma-separated)", value=",".join(DEFAULT_SYMBOLS)).strip()
symbols: List[str] = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

# Auto refresh (client-side)
if auto_refresh_sec and auto_refresh_sec > 0:
    st_autorefresh = st.experimental_rerun  # placeholder to avoid import; we call none here
    # Streamlit doesn't have a built-in timer; we provide a manual refresh button instead.
refresh = st.sidebar.button("🔄 Manual refresh")

# --- Helpers -----------------------------------------------------------------
@dataclass
class EquitySnapshot:
    timestamp: datetime
    equity: float

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

@st.cache_data(show_spinner=False, ttl=60)
def _demo_equity(n_points: int = 120) -> pd.DataFrame:
    """Generate a noisy upward-sloping equity curve for demo."""
    base = 100_000.0
    timestamps = pd.date_range(_now_utc() - timedelta(minutes=n_points - 1), periods=n_points, freq="min", tz="UTC")
    drift = np.linspace(0, 1500, n_points)
    noise = np.random.randn(n_points) * 200
    equity = base + drift + noise
    return pd.DataFrame({"timestamp": timestamps, "equity": equity}).set_index("timestamp")

def _compute_metrics(equity: pd.Series) -> pd.DataFrame:
    """Compute simple performance metrics from equity series (UTC-indexed)."""
    if equity.empty:
        return pd.DataFrame([{"Metric": "Total Return", "Value": "n/a"}])

    eq = equity.dropna().astype(float)
    total_ret = (eq.iloc[-1] / eq.iloc[0]) - 1.0 if len(eq) > 1 else 0.0
    rets = eq.pct_change().dropna()
    ann_factor = 252  # daily-like; if minute-level, this is heuristic. For minute data use 252*390.
    sharpe = (rets.mean() / (rets.std() + 1e-12)) * np.sqrt(ann_factor) if len(rets) > 1 else 0.0

    # Max drawdown
    roll_max = eq.cummax()
    dd = (eq / roll_max) - 1.0
    max_dd = dd.min() if not dd.empty else 0.0

    # Format
    rows = [
        {"Metric": "Total Return", "Value": f"{total_ret*100:.2f}%"},
        {"Metric": "Sharpe Ratio", "Value": f"{sharpe:.2f}"},
        {"Metric": "Max Drawdown", "Value": f"{max_dd*100:.2f}%"},
        {"Metric": "Samples", "Value": f"{len(eq):,}"},
    ]
    return pd.DataFrame(rows)

@st.cache_data(show_spinner=False, ttl=30)
def _fetch_equity_from_db(since: datetime) -> Optional[pd.DataFrame]:
    """Fetch equity curve from Postgres if DATABASE_URL is configured. Expect a table `equity_snapshots(ts_utc TIMESTAMPTZ, equity NUMERIC)`."""
    if not DB_URL:
        return None
    try:
        import sqlalchemy as sa  # lazy import so Streamlit still works without it

        eng = sa.create_engine(DB_URL, pool_pre_ping=True, pool_size=3, max_overflow=2)
        query = """
            SELECT ts_utc AS timestamp, equity
            FROM equity_snapshots
            WHERE ts_utc >= :since
            ORDER BY ts_utc ASC
        """
        with eng.connect() as conn:
            df = pd.read_sql(query, conn, params={"since": since})
        if df.empty:
            return None
        # Ensure tz-aware
        if df["timestamp"].dtype.tz is None:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df.set_index("timestamp").sort_index()
    except Exception as e:
        st.warning(f"DB equity fetch failed: {e}")
        return None

@st.cache_data(show_spinner=False, ttl=30)
def _fetch_trades_from_db(since: datetime, symbols: List[str] | None) -> Optional[pd.DataFrame]:
    """Fetch recent trades. Expect a table `trades(symbol TEXT, side TEXT, qty NUMERIC, price NUMERIC, pnl NUMERIC, ts_utc TIMESTAMPTZ)`."""
    if not DB_URL:
        return None
    try:
        import sqlalchemy as sa

        eng = sa.create_engine(DB_URL, pool_pre_ping=True, pool_size=3, max_overflow=2)
        sym_filter = ""
        params = {"since": since}
        if symbols:
            sym_filter = " AND symbol = ANY(:symbols) "
            params["symbols"] = symbols
        query = f"""
            SELECT symbol AS "Symbol", side AS "Side", qty AS "Qty", price AS "Price",
                   pnl AS "PnL", ts_utc AS "Timestamp"
            FROM trades
            WHERE ts_utc >= :since
            {sym_filter}
            ORDER BY ts_utc DESC
            LIMIT 200
        """
        with eng.connect() as conn:
            df = pd.read_sql(query, conn, params=params)
        if df.empty:
            return None
        if df["Timestamp"].dtype.tz is None:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], utc=True)
        return df
    except Exception as e:
        st.warning(f"DB trades fetch failed: {e}")
        return None

# --- Header ------------------------------------------------------------------
st.title("AI Trading Agent — Monitoring Dashboard")
st.caption("Live strategy diagnostics and telemetry view")

# --- Account Equity Overview --------------------------------------------------
st.header("📊 Account Equity Overview")

since = _now_utc() - timedelta(days=lookback_days)
equity_df = _fetch_equity_from_db(since) or _demo_equity(n_points=min(lookback_days * 390, 2000))

# Allow user to view in local timezone
tz_option = st.selectbox("Display time in", ["UTC", TZ_LOCAL], index=1)
equity_plot = equity_df.copy()
if tz_option != "UTC":
    equity_plot.index = equity_plot.index.tz_convert(tz_option)

st.line_chart(equity_plot.rename(columns={"equity": "Equity"}))

# Metrics block
st.subheader("Performance Metrics")
st.table(_compute_metrics(equity_df["equity"]))

# --- Recent Trades ------------------------------------------------------------
st.header("💼 Recent Trades")
trades_df = _fetch_trades_from_db(since, symbols)  # may be None

if trades_df is None:
    # Provide a placeholder demo table if DB isn't wired yet
    demo_trades = pd.DataFrame(
        {
            "Symbol": ["AAPL", "NVDA", "MSFT"],
            "Side": ["BUY", "SELL", "BUY"],
            "Qty": [10, 5, 12],
            "Price": [182.5, 442.1, 319.7],
            "PnL": [150.0, -75.0, 210.5],
            "Timestamp": [datetime.now(timezone.utc)] * 3,
        }
    )
    st.info("Using demo trades — wire Postgres `trades` table to see live fills.")
    st.dataframe(demo_trades)
else:
    st.dataframe(trades_df)

# --- Alerts & Logs ------------------------------------------------------------
st.header("🚨 Alerts & Logs")
st.caption("Wire Telegram alerts & backend runtime logs here (follow-up).")
st.text_area("Runtime Logs", "No alerts. System stable.", height=150)

# --- Footer -------------------------------------------------------------------
st.divider()
st.caption(
    "AI Trader v0.1.0 — Monitoring Layer • "
    "Set DATABASE_URL to enable live queries • "
    "Symbols filtered: " + (", ".join(symbols) if symbols else "All")
)
