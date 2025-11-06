from __future__ import annotations

from datetime import datetime, timezone

from app.db.repositories.market import MarketRepository


class StubRow:
    def __init__(self, symbol: str, vendor: str, ts: datetime) -> None:
        self.symbol = symbol
        self.vendor = vendor
        self.ts_utc = ts


class StubSession:
    def __init__(self, rows) -> None:
        self._rows = rows

    def scalars(self, stmt):  # pragma: no cover - stmt unused in stub
        return iter(self._rows)

    # Session API compatibility ------------------------------------------------
    def execute(self, *args, **kwargs):  # pragma: no cover - not exercised
        raise NotImplementedError


def test_latest_price_snapshots_prioritises_vendor_order():
    ts_base = datetime.now(timezone.utc)
    rows = [
        StubRow("AAPL", "finnhub", ts_base),
        StubRow("AAPL", "alphavantage", ts_base.replace(minute=ts_base.minute - 1)),
        StubRow("MSFT", "alpaca", ts_base),
    ]
    repo = MarketRepository(StubSession(rows))
    result = repo.latest_price_snapshots(
        ["aapl", "msft"], ["alphavantage", "finnhub", "alpaca"]
    )

    assert set(result.keys()) == {"AAPL", "MSFT"}
    assert result["AAPL"].vendor == "alphavantage"
    assert result["MSFT"].vendor == "alpaca"


def test_latest_price_snapshots_handles_missing_symbols():
    repo = MarketRepository(StubSession([]))
    assert repo.latest_price_snapshots([], ["alpaca"]) == {}
