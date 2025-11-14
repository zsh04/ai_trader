from __future__ import annotations

import math
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from app.agent.risk import FractionalKellyAgent
from app.dal.manager import MarketDataDAL
from app.eventbus.publisher import publish_event
from app.execution.alpaca_client import AlpacaClient, ExecutionError
from app.probability.pipeline import join_probabilistic_features
from app.probability.storage import (
    load_probabilistic_frame,
    persist_probabilistic_frame,
)
from app.strats.breakout import BreakoutParams
from app.strats.params import MeanReversionParams, MomentumParams
from app.telemetry import router as router_telemetry

from .types import RouterContext, RouterRequest

RouterState = Dict[str, Any]


def _ensure_dates(req: RouterRequest, ctx: RouterContext) -> tuple[datetime, datetime]:
    if req.start.tzinfo is None:
        start = req.start.replace(tzinfo=UTC)
    else:
        start = req.start.astimezone(UTC)
    if req.end is None:
        end = datetime.now(tz=UTC)
    elif req.end.tzinfo is None:
        end = req.end.replace(tzinfo=UTC)
    else:
        end = req.end.astimezone(UTC)
    return start, end


def ingest_frame(state: RouterState) -> RouterState:
    with router_telemetry.start_node_span("ingest_frame"):
        if state.get("halt"):
            return state
        req: RouterRequest = state["request"]
        ctx: RouterContext = state["context"]
        start, end = _ensure_dates(req, ctx)
        path = Path(ctx.manifest_root)
        path.mkdir(parents=True, exist_ok=True)

        if ctx.offline_mode:
            synthetic = _synthetic_frame(req.symbol, start, end)
            if synthetic is None:
                state["errors"].append("ingest:synthetic-empty")
                state["halt"] = True
                state["fallback_reason"] = "synthetic_failed"
            else:
                state["frame"] = synthetic
                state["events"].append("ingest:synthetic")
            return state

        cached = load_probabilistic_frame(
            req.symbol,
            req.strategy,
            vendor=req.dal_vendor,
            interval=req.dal_interval.lower(),
            root=path,
        )
        if cached is not None and not cached.empty and not req.use_probabilistic:
            state["frame"] = cached
            state["prob_frame_path"] = str(
                path
                / f"{req.symbol.upper()}_{req.strategy.lower()}_{req.dal_vendor.lower()}_{req.dal_interval.lower()}.parquet"
            )
            state["events"].append("ingest:manifest-hit")
            return state

        dal = state.get("dal_instance")
        if dal is None:
            dal = MarketDataDAL(enable_postgres_metadata=False)
            state["dal_instance"] = dal

        try:
            batch = dal.fetch_bars(
                req.symbol,
                start=start,
                end=end,
                interval=req.dal_interval,
                vendor=req.dal_vendor,
            )
            df = batch.bars.to_dataframe().copy()
            if df.empty:
                raise RuntimeError("empty bar set")
            prob = join_probabilistic_features(
                df, signals=batch.signals, regimes=batch.regimes
            )
            state["frame"] = prob
            path_str = persist_probabilistic_frame(
                req.symbol,
                req.strategy,
                prob,
                vendor=req.dal_vendor,
                interval=req.dal_interval,
                root=path,
                source="router",
            )
            if path_str:
                state["prob_frame_path"] = str(path_str)
            state["events"].append("ingest:dal")
        except Exception as exc:  # pragma: no cover - network/runtime
            logger.warning("Router ingest failed: {}", exc)
            synthetic = _synthetic_frame(req.symbol, start, end)
            if synthetic is not None:
                state["frame"] = synthetic
                state["events"].append("ingest:synthetic")
            else:
                state["errors"].append(f"ingest:{exc}")
                state["halt"] = True
                state["fallback_reason"] = "dal_ingest_failed"
        return state


def infer_priors(state: RouterState) -> RouterState:
    if state.get("halt"):
        return state
    frame: Optional[pd.DataFrame] = state.get("frame")
    if frame is None or frame.empty:
        state["errors"].append("priors:no-frame")
        state["halt"] = True
        state["fallback_reason"] = "no_frame"
        return state
    with router_telemetry.start_node_span("infer_priors"):
        try:
            tail = frame.tail(60)
            returns = (
                tail["close"].pct_change().dropna()
                if "close" in tail.columns
                else pd.Series(dtype=float)
            )
            win_prob = float((returns > 0).mean()) if not returns.empty else 0.55
            vol_hint = float(returns.std()) if not returns.empty else 0.02
            avg_return = float(returns.mean()) if not returns.empty else 0.0
            payoff = max(1.1, 1.0 + abs(avg_return) * 50)
            priors = {
                "win_prob": max(0.05, min(0.95, win_prob)),
                "payoff": payoff,
                "vol_hint": vol_hint,
                "avg_return": avg_return,
                "regime": (
                    tail.get("regime_label").iloc[-1]
                    if "regime_label" in tail.columns
                    else "unknown"
                ),
            }
            state["priors"] = priors
            state["events"].append("priors:computed")
        except Exception as exc:  # pragma: no cover - defensive
            state["errors"].append(f"priors:{exc}")
            state["halt"] = True
            state["fallback_reason"] = "priors_failed"
        return state


def pick_strategy(state: RouterState) -> RouterState:
    if state.get("halt"):
        return state
    req: RouterRequest = state["request"]
    priors = state.get("priors") or {}
    regime = (priors.get("regime") or "").lower()
    strategy = req.strategy
    if regime in {"trend_up", "trend_down"} and req.strategy == "breakout":
        strategy = "momentum"
    elif regime in {"sideways", "calm"} and req.strategy == "breakout":
        strategy = "mean_reversion"
    state["strategy"] = strategy
    state["events"].append(f"strategy:{strategy}")
    params_cls = {
        "breakout": BreakoutParams,
        "momentum": MomentumParams,
        "mean_reversion": MeanReversionParams,
    }.get(strategy, BreakoutParams)
    try:
        state["strategy_params"] = asdict(params_cls(**req.params))
    except Exception:
        state["strategy_params"] = req.params
    return state


def risk_size(state: RouterState) -> RouterState:
    if state.get("halt"):
        return state
    ctx: RouterContext = state["context"]
    req: RouterRequest = state["request"]
    priors = state.get("priors") or {"win_prob": 0.55, "payoff": 1.5}
    with router_telemetry.start_node_span("risk_size"):
        if ctx.kill_switch_active:
            state["events"].append("risk:kill_switch")
            state["halt"] = True
            state["fallback_reason"] = ctx.kill_switch_reason or "kill_switch"
            return state
        agent = FractionalKellyAgent(fraction=ctx.risk_agent_fraction)
        prob = float(priors.get("win_prob", 0.55))
        payoff = float(priors.get("payoff", 1.5))
        frac = agent(probability=prob, payoff=payoff)
        notional = max(
            req.min_notional, min(frac * ctx.kill_switch_notional, req.max_notional)
        )
        if notional >= ctx.kill_switch_notional:
            state["events"].append("risk:kill_switch")
            state["halt"] = True
            state["fallback_reason"] = "kill_switch_notional"
            return state
        state["risk"] = {
            "kelly_fraction": frac,
            "target_notional": notional,
            "probability": prob,
            "payoff": payoff,
        }
        state["events"].append("risk:fractional_kelly")
        return state


def enqueue_order(state: RouterState) -> RouterState:
    if state.get("halt"):
        return state
    req: RouterRequest = state["request"]
    ctx: RouterContext = state["context"]
    risk = state.get("risk") or {}
    frame = state.get("frame")
    price = None
    if isinstance(frame, pd.DataFrame) and not frame.empty and "close" in frame.columns:
        price = float(frame["close"].iloc[-1])
    if price is None or price <= 0:
        price = 100.0
    notional = float(risk.get("target_notional", req.min_notional))
    qty = max(1, math.floor(notional / max(price, 1e-6)))
    intent = {
        "symbol": req.symbol,
        "strategy": state.get("strategy", req.strategy),
        "side": req.side,
        "notional": notional,
        "qty": qty,
        "price_hint": price,
        "run_id": ctx.run_id,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "params": state.get("strategy_params", req.params),
        "risk": risk,
    }
    state["order_intent"] = intent
    if ctx.publish_orders:
        with router_telemetry.start_node_span("publish_order"):
            try:
                publish_event("EH_HUB_ORDERS", intent)
                state["events"].append("order:published")
            except Exception as exc:  # pragma: no cover - fire and forget
                logger.warning("Failed to publish order intent: {}", exc)
                state["errors"].append(f"enqueue:{exc}")
    else:
        state["events"].append("order:simulated")

    if ctx.execute_orders and ctx.alpaca_key and ctx.alpaca_secret:
        client = state.get("_alpaca_client")
        if client is None:
            client = AlpacaClient(
                key=ctx.alpaca_key,
                secret=ctx.alpaca_secret,
                base_url=ctx.alpaca_base_url,
            )
            state["_alpaca_client"] = client
        try:
            with router_telemetry.start_node_span("execute_order"):
                order_id = client.place_bracket_order(
                    symbol=req.symbol,
                    side=req.side,
                    qty=qty,
                    tp_pct=ctx.tp_pct,
                    sl_pct=ctx.sl_pct,
                )
            intent["broker_order_id"] = order_id
            state["events"].append("order:executed")
        except ExecutionError as exc:  # pragma: no cover - depends on broker
            state["errors"].append(f"execution:{exc}")
            state["fallback_reason"] = "execution_failed"
    return state


def annotate_latency(state: RouterState, started_ns: float) -> RouterState:
    elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
    state["latency_ms"] = elapsed_ms
    return state


def _synthetic_frame(
    symbol: str, start: datetime, end: datetime
) -> Optional[pd.DataFrame]:
    try:
        idx = pd.date_range(start, end, freq="D", tz=UTC)
        if len(idx) == 0:
            return None
        base = 100 + hash(symbol) % 25
        prices = pd.Series(range(len(idx)), index=idx) * 0.5 + base
        frame = pd.DataFrame(
            {
                "open": prices + 0.1,
                "high": prices + 0.5,
                "low": prices - 0.5,
                "close": prices,
                "prob_velocity": 0.01,
                "prob_uncertainty": 0.02,
                "regime_label": [
                    "trend_up" if i % 2 == 0 else "calm" for i in range(len(idx))
                ],
            },
            index=idx,
        )
        return frame
    except Exception:  # pragma: no cover
        return None
