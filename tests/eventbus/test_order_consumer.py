from __future__ import annotations

from datetime import datetime

from app.eventbus import order_consumer


def test_intent_to_order_record_defaults():
    payload = {
        "symbol": "AAPL",
        "side": "buy",
        "qty": 5,
        "timestamp": "2025-01-02T15:30:00Z",
    }
    record = order_consumer.intent_to_order_record(payload)
    assert record["symbol"] == "AAPL"
    assert record["side"] == "buy"
    assert record["order_type"] == "market"
    assert record["status"] == "pending"
    assert isinstance(record["submitted_at"], datetime)


def test_intent_to_order_record_executed():
    payload = {
        "symbol": "MSFT",
        "side": "sell",
        "qty": 2,
        "timestamp": "2025-01-02T16:00:00+00:00",
        "broker_order_id": "abc123",
    }
    record = order_consumer.intent_to_order_record(payload)
    assert record["status"] == "executed"
    assert record["broker_order_id"] == "abc123"


def test_intent_to_fill_records_parses_entries():
    payload = {
        "symbol": "NVDA",
        "side": "buy",
        "fills": [
            {
                "qty": 1.5,
                "price": 120.25,
                "filled_at": "2025-02-01T10:00:00Z",
                "fee": 0.12,
            },
            {"qty": 0, "price": 0},  # ignored
        ],
    }
    records = order_consumer.intent_to_fill_records("run-1", payload)
    assert len(records) == 1
    fill = records[0]
    assert fill["order_id"] == "run-1"
    assert fill["symbol"] == "NVDA"
    assert fill["qty"] == 1.5
    assert fill["price"] == 120.25
    assert isinstance(fill["filled_at"], datetime)
