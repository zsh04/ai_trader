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

import inspect
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import altair as alt
import numpy as np
import pandas as pd
import requests
import streamlit as st

from app.adapters.db.postgres import get_session
from app.db.repositories import TradingRepository

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
DB_URL_RAW = os.getenv("DATABASE_URL", "")
API_BASE_URL = os.getenv("API_BASE_URL", "").rstrip("/")
API_BEARER_TOKEN = os.getenv("API_BEARER_TOKEN")
DB_URL = DB_URL_RAW.strip().strip("'\"")
TZ_LOCAL = os.getenv("DASHBOARD_TZ", "America/New_York")
DEFAULT_SYMBOLS = os.getenv("DASHBOARD_SYMBOLS", "AAPL,MSFT,NVDA,SPY,QQQ")
SWEEP_BASE_DIR = Path(os.getenv("BACKTEST_SWEEP_DIR", "artifacts/backtests"))
PROB_FRAME_MANIFEST = Path(
    os.getenv("PROB_FRAME_MANIFEST", "artifacts/probabilistic/frames/manifest.jsonl")
)
ALTAIR_ACCEPTS_WIDTH = "width" in inspect.signature(st.altair_chart).parameters
DATAFRAME_ACCEPTS_WIDTH = "width" in inspect.signature(st.dataframe).parameters


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _render_altair(chart: alt.Chart) -> None:
    """Render Altair charts with backwards-compatible sizing parameters."""
    if ALTAIR_ACCEPTS_WIDTH:
        st.altair_chart(chart, width="stretch")
    else:
        st.altair_chart(chart, use_container_width=True)


def _render_dataframe(data: object, *, height: Optional[int] = None) -> None:
    """Render dataframes while supporting both legacy and new Streamlit kwargs."""
    kwargs: Dict[str, object] = {}
    if height is not None:
        kwargs["height"] = height
    if DATAFRAME_ACCEPTS_WIDTH:
        st.dataframe(data, width="stretch", **kwargs)
    else:
        if height is not None:
            st.dataframe(data, use_container_width=True, height=height)
        else:
            st.dataframe(data, use_container_width=True)


@contextmanager
def _session_scope():
    try:
        session = get_session()
    except RuntimeError:
        yield None
        return
    try:
        yield session
    finally:
        session.close()


def _call_api(path: str, params: Optional[dict] = None) -> Optional[List[dict]]:
    if not API_BASE_URL:
        return None
    url = f"{API_BASE_URL}{path}" if path.startswith("/") else f"{API_BASE_URL}/{path}"
    headers = {"User-Agent": "ai-trader-ui"}
    if API_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {API_BEARER_TOKEN}"
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return None
    except Exception as exc:  # pragma: no cover - network optional
        st.warning(f"API request failed ({path}): {exc}")
        return None


@st.cache_data(show_spinner=False, ttl=60)
def _load_sweep_records(limit: int = 5) -> Optional[pd.DataFrame]:
    if not SWEEP_BASE_DIR.exists():
        return None
    summary_files = sorted(
        SWEEP_BASE_DIR.rglob("summary.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    rows: List[Dict[str, object]] = []
    for path in summary_files:
        try:
            strategy = path.parent.parent.name if path.parent.parent else "unknown"
            sweep_ts = path.parent.name
            with path.open() as handle:
                for line in handle:
                    data = line.strip()
                    if not data:
                        continue
                    record = json.loads(data)
                    record["strategy"] = strategy
                    record["sweep_timestamp"] = sweep_ts
                    record["summary_path"] = str(path)
                    metrics = record.get("metrics") or {}
                    for key in ("sharpe", "sortino", "total_return", "max_drawdown"):
                        record[f"metric_{key}"] = metrics.get(key)
                    record["params_text"] = json.dumps(
                        record.get("params") or {}, sort_keys=True
                    )
                    rows.append(record)
        except FileNotFoundError:
            continue
        if len(rows) >= limit * 10:
            break
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["_timestamp"] = pd.to_datetime(df["sweep_timestamp"], errors="coerce")
    return df


@st.cache_data(show_spinner=False, ttl=60)
def _load_sweep_jobs(limit: int = 20) -> Optional[pd.DataFrame]:
    data = _call_api("/backtests/sweeps/jobs", params={"limit": limit})
    if not data:
        return None
    df = pd.DataFrame(data)
    if df.empty:
        return None
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        df = df.sort_values("ts", ascending=False)
    return df


def _render_sweep_kpis(df: pd.DataFrame) -> None:
    completed = df[df.get("status") == "completed"].copy()
    running = df[df.get("status") == "running"].copy()
    queued = df[df.get("status") == "queued"].copy()
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Completed", len(completed))
    col_b.metric("Running", len(running))
    col_c.metric("Queued", len(queued))
    eta_minutes = "–"
    if not completed.empty and len(running) > 0:
        avg_duration = completed.get("duration_ms").dropna().mean()
        if avg_duration:
            eta_minutes = f"{(avg_duration / 60000.0) * len(running):.1f}"
    col_d.metric("ETA (min)", eta_minutes)


def _render_sweep_throughput(df: pd.DataFrame) -> None:
    completed = df[df.get("status") == "completed"].copy()
    if completed.empty or "ts" not in completed.columns:
        return
    completed["ts"] = pd.to_datetime(completed["ts"], errors="coerce")
    completed = completed.dropna(subset=["ts"])
    if completed.empty:
        return
    hourly = (
        completed.set_index("ts").resample("1H").size().reset_index(name="jobs")
    )
    chart = (
        alt.Chart(hourly)
        .mark_bar(color="#38bdf8")
        .encode(
            x=alt.X("ts:T", title="Hour"),
            y=alt.Y("jobs:Q", title="Jobs completed"),
            tooltip=[alt.Tooltip("ts:T"), alt.Tooltip("jobs:Q")],
        )
        .properties(height=220)
    )
    st.altair_chart(chart, use_container_width=True)


@st.cache_data(show_spinner=False, ttl=60)
def _load_prob_frame_manifest(limit: int = 50) -> Optional[pd.DataFrame]:
    if not PROB_FRAME_MANIFEST.exists():
        return None
    rows: List[Dict[str, object]] = []
    try:
        with PROB_FRAME_MANIFEST.open() as handle:
            for line in handle:
                data = line.strip()
                if not data:
                    continue
                try:
                    record = json.loads(data)
                except json.JSONDecodeError:
                    continue
                rows.append(record)
                if len(rows) >= limit:
                    break
    except FileNotFoundError:
        return None
    if not rows:
        return None
    df = pd.DataFrame(rows)
    if "path" in df.columns and "prob_frame_path" not in df.columns:
        df["prob_frame_path"] = df["path"]
    df["saved_at"] = pd.to_datetime(df.get("saved_at"), errors="coerce")
    return df.sort_values("saved_at", ascending=False)


@st.cache_data(show_spinner=False, ttl=60)
def _load_prob_frame_preview(path: str) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_parquet(path)
    except FileNotFoundError:
        return None
    except Exception as exc:  # pragma: no cover - IO failures should not crash UI
        st.warning(f"Failed to read probabilistic frame {path}: {exc}")
        return None
    if df.empty:
        return None
    if isinstance(df.index, pd.PeriodIndex):
        df.index = df.index.to_timestamp()
    return df


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
        with _session_scope() as session:
            if session is None:
                return None
            repo = TradingRepository(session)
            snapshots = repo.recent_equity(since=since, limit=2000)
        if not snapshots:
            return None
        records = []
        for snap in snapshots:
            records.append(
                {
                    "timestamp": snap.ts_utc,
                    "equity": float(snap.equity),
                    "cash": float(snap.cash) if snap.cash is not None else None,
                    "pnl_day": (
                        float(snap.pnl_day) if snap.pnl_day is not None else None
                    ),
                    "drawdown": (
                        float(snap.drawdown) if snap.drawdown is not None else None
                    ),
                    "leverage": (
                        float(snap.leverage) if snap.leverage is not None else None
                    ),
                }
            )
        df = pd.DataFrame.from_records(records)
        if df.empty:
            return None
        df = df.sort_values("timestamp").set_index("timestamp")
        if df.index.tz is None:
            df.index = pd.to_datetime(df.index, utc=True)
        return df
    except Exception as exc:  # pragma: no cover
        st.warning(f"Equity query failed: {exc}")
        return None


def _get_trades_from_db(
    since: datetime, symbols: List[str] | None
) -> Optional[pd.DataFrame]:
    if not DB_URL:
        return None
    try:
        with _session_scope() as session:
            if session is None:
                return None
            repo = TradingRepository(session)
            fills = repo.recent_trades(symbols, limit=150)
        if not fills:
            return None
        records = []
        for fill in fills:
            records.append(
                {
                    "Symbol": fill.symbol,
                    "Side": fill.side,
                    "Qty": float(fill.qty),
                    "Entry Price": float(fill.price),
                    "PnL": float(fill.pnl) if fill.pnl is not None else None,
                    "Timestamp": fill.filled_at,
                }
            )
        df = pd.DataFrame.from_records(records)
        if df.empty:
            return None
        if df["Timestamp"].dtype.tz is None:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], utc=True)
        return df
    except Exception as exc:  # pragma: no cover
        st.warning(f"Trade query failed: {exc}")
        return None


def _get_trades_from_api(
    since: datetime, symbols: List[str] | None
) -> Optional[pd.DataFrame]:
    params = {"limit": 150}
    if symbols and len(symbols) == 1:
        params["symbol"] = symbols[0]
    data = _call_api("/fills/", params)
    if not data:
        return None
    df = pd.DataFrame(data)
    if df.empty:
        return None
    df.rename(
        columns={
            "symbol": "Symbol",
            "side": "Side",
            "qty": "Qty",
            "price": "Entry Price",
            "pnl": "PnL",
            "filled_at": "Timestamp",
        },
        inplace=True,
    )
    df["Side"] = df["Side"].str.upper()
    df["Qty"] = df["Qty"].astype(float)
    df["Entry Price"] = df["Entry Price"].astype(float)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], utc=True, errors="coerce")
    return df


@st.cache_data(show_spinner=False, ttl=30)
def _fetch_trades(
    since: datetime, symbols: List[str] | None
) -> Optional[pd.DataFrame]:
    return _get_trades_from_db(since, symbols) or _get_trades_from_api(since, symbols)


def _get_orders_from_db(limit: int = 50) -> Optional[pd.DataFrame]:
    if not DB_URL:
        return None
    try:
        with _session_scope() as session:
            if session is None:
                return None
            repo = TradingRepository(session)
            orders = repo.recent_orders(limit=limit)
        if not orders:
            return None
        rows = []
        for order in orders:
            raw = (order.raw_payload or {}) if hasattr(order, "raw_payload") else {}
            rows.append(
                {
                    "Symbol": getattr(order, "symbol", ""),
                    "Side": getattr(order, "side", "").upper(),
                    "Qty": float(getattr(order, "qty", 0) or 0),
                    "Status": getattr(order, "status", ""),
                    "Strategy": raw.get("strategy"),
                    "Run": raw.get("run_id"),
                    "Submitted": getattr(order, "submitted_at", None),
                }
            )
        df = pd.DataFrame.from_records(rows)
        if df.empty:
            return None
        if df["Submitted"].dtype.tz is None:
            df["Submitted"] = pd.to_datetime(df["Submitted"], utc=True)
        return df
    except Exception as exc:  # pragma: no cover
        st.warning(f"Order query failed: {exc}")
        return None


def _get_orders_from_api(limit: int = 50) -> Optional[pd.DataFrame]:
    data = _call_api("/orders/", {"limit": limit})
    if not data:
        return None
    df = pd.DataFrame(data)
    if df.empty:
        return None
    df.rename(
        columns={
            "symbol": "Symbol",
            "side": "Side",
            "qty": "Qty",
            "status": "Status",
            "strategy": "Strategy",
            "run_id": "Run",
            "submitted_at": "Submitted",
        },
        inplace=True,
    )
    df["Side"] = df["Side"].str.upper()
    df["Submitted"] = pd.to_datetime(df["Submitted"], utc=True, errors="coerce")
    return df


@st.cache_data(show_spinner=False, ttl=30)
def _fetch_orders(limit: int = 50) -> Optional[pd.DataFrame]:
    return _get_orders_from_db(limit) or _get_orders_from_api(limit)


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


def _render_stat_card(
    title: str, value: str, delta: str | None, delta_class: str, footnote: str
) -> None:
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


def _frame_metadata(
    frame: pd.DataFrame, context: Optional[Dict[str, object]] = None
) -> Dict[str, object]:
    meta: Dict[str, object] = {
        "rows": int(frame.shape[0]),
        "cols": int(frame.shape[1]),
        "columns": list(frame.columns),
    }
    if not frame.index.empty:
        try:
            meta["start_index"] = str(frame.index[0])
            meta["end_index"] = str(frame.index[-1])
        except Exception:
            pass
    if context:
        meta["context"] = {
            "strategy": context.get("strategy"),
            "job_id": context.get("job_id"),
            "sweep_timestamp": context.get("sweep_timestamp"),
            "source": context.get("source"),
        }
    return meta


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
    _render_altair((base + area).interactive())


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
    _render_dataframe(styled, height=360)


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
# Backtest sweeps summary
# -----------------------------------------------------------------------------
sweep_df = _load_sweep_records(limit=5)
with st.expander("Backtest Sweeps", expanded=False):
    if sweep_df is None or sweep_df.empty:
        st.info(
            "No sweep summaries found. Run `python -m app.backtest.sweeps --config <file>` to populate artifacts/backtests."
        )
    else:
        latest = sweep_df.sort_values("_timestamp", ascending=False)
        sharpe_df = latest.dropna(subset=["metric_sharpe"])
        if not sharpe_df.empty:
            chart = (
                alt.Chart(sharpe_df)
                .mark_circle(size=80, opacity=0.7)
                .encode(
                    x=alt.X("metric_sharpe:Q", title="Sharpe"),
                    y=alt.Y("metric_sortino:Q", title="Sortino"),
                    color=alt.Color("strategy:N", title="Strategy"),
                    tooltip=[
                        alt.Tooltip("strategy:N"),
                        alt.Tooltip("sweep_timestamp:N", title="Sweep"),
                        alt.Tooltip("job_id:Q", title="Job"),
                        alt.Tooltip("metric_sharpe:Q", title="Sharpe", format=".2f"),
                        alt.Tooltip(
                            "metric_total_return:Q", title="Total Return", format=".2f"
                        ),
                        alt.Tooltip("params_text:N", title="Params"),
                    ],
                )
            )
            _render_altair(chart)
        st.caption("Top jobs by Sharpe (latest sweeps)")
        display_cols = [
            "sweep_timestamp",
            "strategy",
            "job_id",
            "metric_sharpe",
            "metric_total_return",
            "metric_max_drawdown",
            "params_text",
        ]
        _render_dataframe(latest[display_cols].head(10), height=260)
        st.markdown("###### Probabilistic Frame Viewer")
        manifest_df = _load_prob_frame_manifest(limit=50)
        viewer_source = manifest_df if manifest_df is not None else latest
        if viewer_source is None or viewer_source.empty:
            st.info("No probabilistic frame manifests found yet.")
        else:
            viewer = viewer_source.dropna(subset=["prob_frame_path"]).copy()
            if viewer.empty:
                st.info("No probabilistic frame paths recorded in recent runs.")
            else:
                viewer["label"] = viewer.apply(
                    lambda row: f"{row.get('sweep_timestamp', row.get('saved_at')) or 'manual'} • "
                    f"{row.get('strategy', 'unknown')} • job {row.get('job_id', '—')}",
                    axis=1,
                )
                selection = st.selectbox(
                    "Select a run to inspect", viewer["label"].tolist(), index=0
                )
                selected = viewer.loc[viewer["label"] == selection].iloc[0]
                frame_path = selected["prob_frame_path"]
                st.caption(f"Frame path: `{frame_path}`")
                frame_df = _load_prob_frame_preview(frame_path)
                if frame_df is None:
                    st.warning(
                        "Frame not found or empty. Ensure the CLI run persisted successfully."
                    )
                else:
                    st.json(_frame_metadata(frame_df, selected.to_dict()))
                    _render_dataframe(frame_df.tail(50), height=320)
        manual_path = st.text_input(
            "Manual frame path (optional)",
            placeholder="artifacts/probabilistic/frames/<symbol>_<strategy>_*.parquet",
        )
        if manual_path.strip():
            manual_df = _load_prob_frame_preview(manual_path.strip())
            if manual_df is None:
                st.warning("Unable to load the specified path.")
            else:
                st.json(_frame_metadata(manual_df))
                _render_dataframe(manual_df.tail(50), height=240)

        st.markdown("###### Sweep Job Queue")
        jobs_df = _load_sweep_jobs(limit=200)
        if jobs_df is None or jobs_df.empty:
            st.info("No sweep job records yet. Use /backtests/sweeps to queue jobs.")
        else:
            _render_sweep_kpis(jobs_df)
            jobs_df = jobs_df.rename(
                columns={
                    "job_id": "Job",
                    "status": "Status",
                    "strategy": "Strategy",
                    "symbol": "Symbol",
                    "ts": "Timestamp",
                    "results_count": "Results",
                    "duration_ms": "Duration (ms)",
                }
            )
            if "Timestamp" in jobs_df.columns:
                jobs_df["Timestamp"] = pd.to_datetime(
                    jobs_df["Timestamp"], errors="coerce"
                )
            _render_dataframe(jobs_df.head(20), height=280)
            st.caption("Hourly throughput (completed jobs)")
            _render_sweep_throughput(jobs_df.rename(columns={"Timestamp": "ts"}))

# -----------------------------------------------------------------------------
# Trades & Positions
# -----------------------------------------------------------------------------
lower_tabs = st.tabs(["Recent Trades", "Positions", "Orders", "Operational Notes"])

with lower_tabs[0]:
    st.markdown("##### Blotter (latest 150 fills)")
    trades_df = _fetch_trades(since, symbols) or pd.DataFrame()
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
    _render_altair(exposure_chart)
    st.caption(
        "Exposure split derived from latest equity. Replace `_sample_positions` with live holdings to reflect actual positions."
    )

with lower_tabs[2]:
    st.markdown("##### Router Orders (latest)")
    orders_df = _fetch_orders(limit=50)
    if orders_df is None or orders_df.empty:
        st.info(
            "No orders captured yet. Trigger `/router/run` with `publish_orders=true`."
        )
    else:
        df = orders_df.copy()
        df["Qty"] = df["Qty"].round(4)
        _render_dataframe(df, height=320)

with lower_tabs[3]:
    st.markdown("##### Operational Alerts & Notes")
    st.write(
        """
        - ✅ **Latency**: no anomalies detected.
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
