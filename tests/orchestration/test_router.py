from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.orchestration import nodes
from app.orchestration.router import run_router
from app.orchestration.types import RouterContext, RouterRequest


def _request(symbol: str = "AAPL") -> RouterRequest:
    now = datetime(2025, 1, 2, tzinfo=UTC)
    return RouterRequest(symbol=symbol, start=now - timedelta(days=10), end=now)


def test_router_offline_mode_produces_synthetic_order():
    req = _request()
    ctx = RouterContext(offline_mode=True)
    result = run_router(req, ctx)
    assert result.order_intent is not None
    assert "ingest:synthetic" in result.events
    assert result.order_intent["qty"] >= 1


def test_router_fallback_when_dal_fails(monkeypatch):
    class FailingDAL:
        def __init__(self, *args, **kwargs):
            pass

        def fetch_bars(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(nodes, "MarketDataDAL", lambda *a, **k: FailingDAL())
    req = _request(symbol="MSFT")
    ctx = RouterContext()
    result = run_router(req, ctx)
    assert result.order_intent is not None
    assert "ingest:synthetic" in result.events
    assert result.fallback_reason != "dal_ingest_failed"


def test_router_execute_orders_requires_keys():
    req = _request("NVDA")
    ctx = RouterContext(execute_orders=True, alpaca_key=None, alpaca_secret=None)
    result = run_router(req, ctx)
    # Without keys, execution is skipped but pipeline still succeeds.
    assert "order:simulated" in result.events
    assert "order:executed" not in result.events


def test_router_kill_switch_active(monkeypatch):
    req = _request("MSFT")
    ctx = RouterContext(
        offline_mode=True, kill_switch_active=True, kill_switch_reason="ops"
    )
    result = run_router(req, ctx)
    assert result.fallback_reason == "ops"
    assert "risk:kill_switch" in result.events
    assert result.order_intent is None


def test_router_publish_orders(monkeypatch):
    calls = []

    def _fake_publish(hub, payload):
        calls.append((hub, payload))

    monkeypatch.setattr(nodes, "publish_event", _fake_publish)
    req = _request("AAPL")
    ctx = RouterContext(offline_mode=True, publish_orders=True)
    result = run_router(req, ctx)
    assert any(event.startswith("order:") for event in result.events)
    assert calls and calls[0][0] == "EH_HUB_ORDERS"
