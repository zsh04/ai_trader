from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.db.repositories.trading import TradingRepository


class DummySnapshot:
    def __init__(self, ts: datetime, equity: float) -> None:
        self.ts_utc = ts
        self.equity = equity
        self.cash = None
        self.pnl_day = None
        self.drawdown = None
        self.leverage = None


class DummyFill:
    def __init__(self, symbol: str, side: str = "buy") -> None:
        self.symbol = symbol
        self.side = side
        self.qty = 1
        self.price = 1.0
        self.pnl = 0.0
        self.filled_at = datetime.now(timezone.utc)


def test_recent_equity_returns_chronological_order():
    ts = datetime.now(timezone.utc)
    snapshots = [
        DummySnapshot(ts, 100),
        DummySnapshot(ts - timedelta(minutes=1), 95),
        DummySnapshot(ts - timedelta(minutes=2), 90),
    ]
    session = MagicMock()
    session.scalars.return_value = iter(snapshots)

    repo = TradingRepository(session)
    result = repo.recent_equity(limit=3)

    assert [snap.equity for snap in result] == [90, 95, 100]


def test_recent_trades_filters_symbols():
    fills = [DummyFill("AAPL"), DummyFill("MSFT"), DummyFill("AAPL")]
    session = MagicMock()
    session.scalars.return_value = iter(fills)

    repo = TradingRepository(session)
    result = repo.recent_trades(["AAPL"], limit=10)

    # Ensure the statement included a WHERE clause for the requested symbols.
    stmt = session.scalars.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE" in compiled and "AAPL" in compiled
    assert list(result) == fills  # iterator exhausted in the call
