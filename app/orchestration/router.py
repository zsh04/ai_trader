from __future__ import annotations

import argparse
import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Iterable, Optional

from langgraph.graph import END, StateGraph
from loguru import logger

from app.telemetry import router as router_telemetry

from . import nodes
from .types import RouterContext, RouterRequest, RouterResult


def _initial_state(request: RouterRequest, context: RouterContext) -> Dict[str, Any]:
    start_ns = time.perf_counter_ns()
    return {
        "request": request,
        "context": context,
        "events": [],
        "errors": [],
        "halt": False,
        "started_ns": start_ns,
    }


def build_router_graph() -> StateGraph:
    graph = StateGraph(dict)
    graph.add_node("ingest_frame", nodes.ingest_frame)
    graph.add_node("infer_priors", nodes.infer_priors)
    graph.add_node("pick_strategy", nodes.pick_strategy)
    graph.add_node("risk_size", nodes.risk_size)
    graph.add_node("enqueue_order", nodes.enqueue_order)

    graph.set_entry_point("ingest_frame")
    graph.add_edge("ingest_frame", "infer_priors")
    graph.add_edge("infer_priors", "pick_strategy")
    graph.add_edge("pick_strategy", "risk_size")
    graph.add_edge("risk_size", "enqueue_order")
    graph.add_edge("enqueue_order", END)
    return graph.compile()


_ROUTER = build_router_graph()


def run_router(
    request: RouterRequest, context: Optional[RouterContext] = None
) -> RouterResult:
    ctx = context or RouterContext()
    state = _initial_state(request, ctx)
    attributes = {
        "symbol": request.symbol,
        "strategy": request.strategy,
        "run_id": ctx.run_id,
    }
    with router_telemetry.start_router_span(attributes):
        final_state = _ROUTER.invoke(state)
        router_telemetry.record_run(attributes)
    nodes.annotate_latency(final_state, state["started_ns"])
    return RouterResult(
        run_id=ctx.run_id,
        symbol=request.symbol,
        strategy=final_state.get("strategy", request.strategy),
        latency_ms=final_state.get("latency_ms", 0.0),
        order_intent=final_state.get("order_intent"),
        prob_frame_path=final_state.get("prob_frame_path"),
        priors=final_state.get("priors"),
        events=list(final_state.get("events", [])),
        errors=list(final_state.get("errors", [])),
        fallback_reason=final_state.get("fallback_reason"),
    )


def _random_request() -> RouterRequest:
    # nosec B311: pseudo-randomness is acceptable for the harness
    symbol = random.choice(["AAPL", "MSFT", "NVDA", "QQQ", "SPY"])  # nosec B311
    now = datetime.now(tz=UTC)
    start = now - timedelta(days=random.randint(30, 90))  # nosec B311
    strategy = random.choice(["breakout", "momentum", "mean_reversion"])  # nosec B311
    params: Dict[str, Any] = {
        "lookback": random.randint(10, 30),  # nosec B311
        "atr_len": random.randint(5, 20),  # nosec B311
        "atr_mult": round(random.uniform(1.0, 3.0), 2),  # nosec B311
    }
    return RouterRequest(
        symbol=symbol,
        start=start,
        end=now,
        strategy=strategy,
        params=params,
        dal_vendor=random.choice(["alpaca", "yahoo", "alphavantage"]),  # nosec B311
        dal_interval=random.choice(["1Day", "5Min"]),  # nosec B311
        side=random.choice(
            ["buy", "buy"]
        ),  # nosec B311 bias to long until short logic lands
    )


def sample_harness(runs: int = 100) -> Iterable[RouterResult]:
    for _ in range(runs):
        request = _random_request()
        context = RouterContext(offline_mode=True)
        result = run_router(request, context)
        logger.info(
            "[router] run_id={} symbol={} strategy={} latency={:.2f}ms events={} errors={}",
            result.run_id,
            result.symbol,
            result.strategy,
            result.latency_ms,
            ",".join(result.events),
            ",".join(result.errors),
        )
        yield result


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph router harness")
    parser.add_argument(
        "--runs",
        type=int,
        default=100,
        help="Number of sample runs to execute (default: 100)",
    )
    args = parser.parse_args()
    results = list(sample_harness(args.runs))
    fallbacks = sum(1 for r in results if r.fallback_reason)
    logger.info(
        "Router harness complete: runs=%s fallbacks=%s avg_latency=%.2fms",
        len(results),
        fallbacks,
        sum(r.latency_ms for r in results) / max(len(results), 1),
    )


if __name__ == "__main__":
    main()
