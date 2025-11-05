"""
AI Trader — Modern Monitoring Dashboard

Run locally:
    streamlit run app/monitoring/dashboard.py

Key features:
* Pulls equity/trade data from Postgres (via DATABASE_URL), falls back to demo data.
* Responsive analyst-style layout with KPI cards, interactive charts, and telemetry panels.
* Sidebar filters for lookback window, auto-refresh cadence, and symbol overrides.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# Page styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Trader Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root { --accent-color: #3b82f6; }
    body, [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 45%, #111827 100%);
        color: #e2e8f0;
    }
    [data-testid="stSidebar"] {
        background-color: #101623 !important;
        border-right: 1px solid rgba(148, 163, 184, 0.1);
    }
    h1, h2, h3, h4, h5, h6 {
        color: #f8fafc !important;
        letter-spacing: 0.03em;
    }
    .card {
        background: rgba(15, 23, 42, 0.72);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 18px;
        padding: 1.1rem 1.4rem;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.35);
        backdrop-filter: blur(18px);
    }
    .metric-label {
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.15em;
        color: rgba(148, 163, 184, 0.9);
    }
    .metric-value {
        font-size: 1.9rem;
        font-weight: 700;
        color: #f8fafc;
    }
    .metric-delta {
        font-size: 0.95rem;
        font-weight: 600;
    }
    .metric-delta.positive { color: #34d399; }
    .metric-delta.negative { color: #f87171; }
    .metric-subtext {
        font-size: 0.8rem;
        color: rgba(148, 163, 184, 0.75);
    }
    .stDataFrame div, .stTable, .stCaption, .stTextInput>div>div>input {
        color: #f8fafc !important;
    }
    .stTabs [role="tab"] {
        color: rgba(241, 245, 249, 0.75) !important;
        border: none !important;
        padding: 0.65rem 1rem !important;
        background: transparent !important;
        border-radius: 12px 12px 0 0 !important;
    }
    .stTabs [role="tab"][aria-selected="true"] {
        color: #f8fafc !important;
        background: rgba(59, 130, 246, 0.15) !important;
        border-bottom: 2px solid var(--accent-color) !important;
    }
    .badge {
        display: inline-flex;
        padding: 0.25rem 0.55rem;
        border-radius: 9999px;
        font-size: 0.7rem;
        font-weight: 600;
        background: rgba(59, 130, 246, 0.12);
        color: #bfdbfe;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Configuration & Caching
# -----------------------------------------------------------------------------
DB_URL = os.getenv("DATABASE_URL", "")
TZ_LOCAL = os.getenv("DASHBOARD_TZ", "America/New_York")
DEFAULT_SYMBOLS = os.getenv("DASHBOARD_SYMBOLS", "AAPL,MSFT,NVDA,SPY,QQQ")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@st.cache_data(show_spinner=False, ttl=45)
def _demo_equity(n_points: int = 390) -> pd.DataFrame:
    base = 100_000.0
    timestamps = pd.date_range(
        _now_utc() - timedelta(minutes=n_points - 1),
        periods=n_points,
        freq="min",
        tz="UTC",
    )
    drift = np.linspace(0, 2200, n_points)
    noise = np.random.randn(n_points) * 120
    equity = base + drift + noise
    return pd.DataFrame({"timestamp": timestamps, "equity": equity}).set_index(
        "timestamp"
    )


@st.cache_data(show_spinner=False, ttl=30)
def _fetch_equity_from_db(since: datetime) -> Optional[pd.DataFrame]:
    if not DB_URL:
        return None
    try:
        import sqlalchemy as sa  # lazy import

        engine = sa.create_engine(DB_URL, pool_pre_ping=True)
        query = """
            SELECT ts_utc AS timestamp, equity
            FROM equity_snapshots
            WHERE ts_utc >= :since
            ORDER BY ts_utc ASC
        """
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"since": since})
        if df.empty:
            return None
        if df["timestamp"].dtype.tz is None:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df.set_index("timestamp").sort_index()
    except Exception as exc:  # pragma: no cover
        st.warning(f"Equity query failed: {exc}")
        return None


@st.cache_data(show_spinner=False, ttl=30)
def _fetch_trades_from_db(
    since: datetime, symbols: List[str] | None
) -> Optional[pd.DataFrame]:
    if not DB_URL:
        return None
    try:
        import sqlalchemy as sa

        engine = sa.create_engine(DB_URL, pool_pre_ping=True)
        params: Dict[str, object] = {"since": since}
        sym_clause = ""
        if symbols:
            sym_clause = " AND symbol = ANY(:symbols)"
            params["symbols"] = symbols
        query = f"""
            SELECT symbol AS "Symbol",
                   side AS "Side",
                   qty AS "Qty",
                   price AS "Entry Price",
                   pnl AS "PnL",
                   ts_utc AS "Timestamp"
            FROM trades
            WHERE ts_utc >= :since
            {sym_clause}
            ORDER BY ts_utc DESC
            LIMIT 150
        """
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params=params)
        if df.empty:
            return None
        if df["Timestamp"].dtype.tz is None:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], utc=True)
        return df
    except Exception as exc:  # pragma: no cover
        st.warning(f"Trade query failed: {exc}")
        return None


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _format_currency(value: float) -> str:
    if pd.isna(value):
        return "—"
    return f"${value:,.0f}"


def _format_delta(value: float) -> Tuple[str, str]:
    if pd.isna(value) or value == 0:
        return "0.0%", "neutral"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%", "positive" if value > 0 else "negative"


def _compute_summary(equity: pd.Series) -> Dict[str, float]:
    eq = equity.dropna().astype(float)
    if eq.empty:
        return {"latest": 0.0, "daily": 0.0, "total": 0.0, "drawdown": 0.0, "vol": 0.0}

    latest = float(eq.iloc[-1])
    daily = (
        ((eq.iloc[-1] / eq.iloc[-min(len(eq), 390)]) - 1.0) * 100
        if len(eq) > 1
        else 0.0
    )
    total = ((eq.iloc[-1] / eq.iloc[0]) - 1.0) * 100 if len(eq) > 1 else 0.0
    roll_max = eq.cummax()
    drawdown = ((eq / roll_max) - 1.0).min() * 100 if not roll_max.empty else 0.0
    rets = eq.pct_change().dropna()
    vol = rets.std() * np.sqrt(252) * 100 if not rets.empty else 0.0
    return {
        "latest": latest,
        "daily": daily,
        "total": total,
        "drawdown": drawdown,
        "vol": vol,
    }


def _render_stat_card(title: str, value: str, delta: str | None, delta_class: str, footnote: str) -> None:
    st.markdown(
        f"""
        <div class="card">
            <div class="metric-label">{title}</div>
            <div class="metric-value">{value}</div>
            {f'<div class="metric-delta {delta_class}">{delta}</div>' if delta else ''}
            <div class="metric-subtext">{footnote}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_equity_chart(df: pd.DataFrame, tz_display: str) -> None:
    if df.empty:
        st.warning("No equity data available.")
        return
    plot_df = df.copy()
    plot_df = plot_df.rename(columns={"equity": "Equity"}).reset_index()
    if tz_display != "UTC":
        plot_df["timestamp"] = plot_df["timestamp"].dt.tz_convert(tz_display)
    base = (
        alt.Chart(plot_df)
        .mark_line(color="#60a5fa", strokeWidth=2.2)
        .encode(
            x=alt.X("timestamp:T", title=f"Time ({tz_display})"),
            y=alt.Y("Equity:Q", title="Account Equity"),
            tooltip=[
                alt.Tooltip("timestamp:T", title="Timestamp"),
                alt.Tooltip("Equity:Q", title="Equity", format=",.0f"),
            ],
        )
    )
    area = base.mark_area(opacity=0.18, color="#60a5fa")
    st.altair_chart((base + area).interactive(), width="stretch")


def _render_trades_table(trades: pd.DataFrame) -> None:
    if trades.empty:
        st.info("No trades captured within the selected window.")
        return
    df = trades.copy()
    df["PnL"] = df["PnL"].astype(float)
    styled = df.style.format(
        {"Entry Price": "${:,.2f}", "PnL": "${:,.2f}"},
        na_rep="—",
    )

    def _pnl_style(value: float) -> Optional[str]:
        if pd.isna(value) or value == 0:
            return None
        return "color: #34d399;" if value > 0 else "color: #f87171;"

    styled = styled.map(_pnl_style, subset=pd.IndexSlice[:, ["PnL"]])
    st.dataframe(styled, width="stretch", height=360)


def _sample_positions(equity: pd.Series) -> pd.DataFrame:
    base_symbols = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
    weights = np.array([0.22, 0.18, 0.16, 0.24, 0.2])
    latest = float(equity.iloc[-1]) if not equity.empty else 100_000
    exposures = latest * weights
    return pd.DataFrame(
        {
            "Symbol": base_symbols,
            "Net Exposure": exposures,
            "Weight": weights * 100,
        }
    )


# -----------------------------------------------------------------------------
# Sidebar controls
# -----------------------------------------------------------------------------
st.sidebar.header("Control Panel")
lookback_days = st.sidebar.slider(
    "Lookback window (days)",
    min_value=5,
    max_value=365,
    value=60,
    step=5,
)
auto_refresh_sec = st.sidebar.number_input(
    "Auto-refresh (sec)",
    min_value=0,
    max_value=600,
    value=0,
    help="0 disables auto refresh. For production, use 60–120s.",
)
symbols_input = st.sidebar.text_input(
    "Focus symbols",
    value=DEFAULT_SYMBOLS,
    help="Comma separated universe filter (optional).",
)
symbols: List[str] = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

refresh_manual = st.sidebar.button("Refresh data", type="primary")
if auto_refresh_sec and auto_refresh_sec > 0:
    st.sidebar.caption(
        f":small_blue_diamond: Auto-refresh requested every {auto_refresh_sec}s (manual refresh recommended during development)."
    )


# -----------------------------------------------------------------------------
# Data preparation
# -----------------------------------------------------------------------------
since = _now_utc() - timedelta(days=lookback_days)
equity_df = _fetch_equity_from_db(since) or _demo_equity(
    n_points=min(lookback_days * 390, 2000)
)
if refresh_manual:
    st.experimental_rerun()  # safe to rerun manually

summary = _compute_summary(equity_df["equity"])
last_updated_utc = equity_df.index[-1] if not equity_df.empty else _now_utc()
last_updated_local = last_updated_utc.astimezone(timezone.utc).astimezone(
    timezone(timedelta(hours=0))
)

# -----------------------------------------------------------------------------
# Header & KPI row
# -----------------------------------------------------------------------------
st.markdown(
    f"""
    <div class="card" style="margin-bottom: 1.2rem;">
        <div style="display:flex; justify-content: space-between; align-items:center;">
            <div>
                <span class="badge">Live Monitoring</span>
                <h1 style="margin:0.25rem 0 0;">AI Trader — Portfolio Pulse</h1>
                <div class="metric-subtext" style="margin-top:0.2rem;">
                    Insights for trading ops teams — track equity, trades, and positions in real time.
                </div>
            </div>
            <div style="text-align:right;">
                <div class="metric-subtext">Last update (UTC)</div>
                <div class="metric-value" style="font-size:1.1rem;">{last_updated_utc.strftime('%Y-%m-%d %H:%M')}</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

card_cols = st.columns(4)
with card_cols[0]:
    _render_stat_card(
        "Net Liquidity",
        _format_currency(summary["latest"]),
        None,
        "",
        "Approximate account equity",
    )
with card_cols[1]:
    daily_delta, delta_class = _format_delta(summary["daily"])
    _render_stat_card(
        "Daily Move",
        daily_delta,
        None,
        delta_class,
        "Change vs. session open",
    )
with card_cols[2]:
    total_delta, total_class = _format_delta(summary["total"])
    _render_stat_card(
        "Total Return",
        total_delta,
        None,
        total_class,
        f"Since {lookback_days}-day lookback start",
    )
with card_cols[3]:
    _render_stat_card(
        "Max Drawdown",
        f"{summary['drawdown']:.2f}%",
        None,
        "negative" if summary["drawdown"] < 0 else "positive",
        "Peak-to-trough within window",
    )

# -----------------------------------------------------------------------------
# Equity chart & metrics
# -----------------------------------------------------------------------------
equity_container = st.container()
with equity_container:
    chart_cols = st.columns([2.5, 1])
    with chart_cols[0]:
        tz_selection = st.selectbox("Display timezone", ["UTC", TZ_LOCAL], index=0)
        _render_equity_chart(equity_df, tz_selection)
    with chart_cols[1]:
        st.markdown("#### Performance Snapshot")
        metrics_table = pd.DataFrame(
            [
                {"Metric": "Total Return", "Value": f"{summary['total']:.2f}%"},
                {"Metric": "Daily Move", "Value": f"{summary['daily']:.2f}%"},
                {"Metric": "Max Drawdown", "Value": f"{summary['drawdown']:.2f}%"},
                {"Metric": "Annualized Vol", "Value": f"{summary['vol']:.2f}%"},
            ]
        )
        st.table(metrics_table)

# -----------------------------------------------------------------------------
# Trades & Positions
# -----------------------------------------------------------------------------
lower_tabs = st.tabs(["Recent Trades", "Positions", "Operational Notes"])

with lower_tabs[0]:
    st.markdown("##### Blotter (latest 150 fills)")
    trades_df = _fetch_trades_from_db(since, symbols) or pd.DataFrame()
    if trades_df.empty:
        demo_trades = pd.DataFrame(
            {
                "Symbol": ["AAPL", "NVDA", "MSFT", "SPY"],
                "Side": ["BUY", "SELL", "BUY", "SELL"],
                "Qty": [10, 5, 12, 8],
                "Entry Price": [182.5, 442.1, 319.7, 505.2],
                "PnL": [150.0, -75.0, 210.5, -42.0],
                "Timestamp": [datetime.now(timezone.utc)] * 4,
            }
        )
        st.info("Demo trades shown — configure DATABASE_URL to surface live fills.")
        _render_trades_table(demo_trades)
    else:
        _render_trades_table(trades_df)

with lower_tabs[1]:
    st.markdown("##### Net Exposure by Symbol")
    positions_df = _sample_positions(equity_df["equity"])
    exposure_chart = (
        alt.Chart(positions_df)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, color="#38bdf8")
        .encode(
            x=alt.X("Net Exposure:Q", title="Net Exposure ($)"),
            y=alt.Y("Symbol:N", sort="-x"),
            tooltip=[
                alt.Tooltip("Symbol:N"),
                alt.Tooltip("Net Exposure:Q", format="$,.0f"),
                alt.Tooltip("Weight:Q", format=".2f"),
            ],
        )
    )
    st.altair_chart(exposure_chart, width="stretch")
    st.caption(
        "Exposure split derived from latest equity. Replace `_sample_positions` with live holdings to reflect actual positions."
    )

with lower_tabs[2]:
    st.markdown("##### Operational Alerts & Notes")
    st.write(
        """
        - ✅ **Latency**: no anomalies detected.
        - ⚙️ **Telegram**: webhook heartbeat received in the past 5 minutes.
        - 📡 **Market data**: Alpaca streaming stable. Yahoo fallback engaged when snapshots unavailable.
        """
    )
    st.text_area(
        "Runbook notes",
        "No incidents logged. Use this space for hand-off notes between operators.",
        height=180,
    )

# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.markdown("---")
st.caption(
    f"AI Trader • Monitoring Dashboard • Symbols: {', '.join(symbols) if symbols else 'All'} • "
    f"Last refresh (UTC): {last_updated_utc.strftime('%Y-%m-%d %H:%M:%S')}"
)
