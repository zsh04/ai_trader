from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest

from app.agent.probabilistic.regime import RegimeSnapshot
from app.backtest.run_breakout import run as breakout_run
from app.dal.results import ProbabilisticBatch
from app.dal.schemas import Bar, Bars, SignalFrame
from app.dal.vendors.base import FetchRequest, VendorClient


@dataclass
class _FakeMetrics:
    sharpe: float = 1.0
    sortino: float = 1.0


class _FakeBetaWinrate:
    def __init__(self) -> None:
        self.fmax = 0.5

    def kelly_fraction(self) -> float:
        return 0.2


class _FakeBacktestEngine:
    def __init__(self) -> None:
        self.last_kwargs: Dict[str, Any] | None = None

    def __call__(self, **kwargs: Any) -> Dict[str, Any]:
        self.last_kwargs = kwargs
        index = pd.date_range("2021-01-01", periods=5, freq="D")
        equity = pd.Series(
            np.linspace(100.0, 105.0, len(index)), index=index, name="equity"
        )
        return {"equity": equity, "trades": []}


class _HybridVendor(VendorClient):
    def __init__(
        self, bars: Bars, signals: List[SignalFrame], regimes: List[RegimeSnapshot]
    ) -> None:
        super().__init__("hybrid")
        self._batch = ProbabilisticBatch(bars=bars, signals=signals, regimes=regimes)
        self.fetch_called_with: Dict[str, Any] | None = None

    def fetch_bars(self, request: FetchRequest) -> Bars:
        self.fetch_called_with = {
            "symbol": request.symbol,
            "start": request.start,
            "end": request.end,
            "interval": request.interval,
        }
        return self._batch.bars

    def to_probabilistic_batch(self) -> ProbabilisticBatch:
        return self._batch


class _FakeMarketDataDAL:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.vendor: _HybridVendor = kwargs.pop(
            "vendor"
        )  # injected via monkeypatch closure

    def fetch_bars(
        self,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1Day",
        vendor: str = "alpaca",
        limit: int | None = None,
    ) -> ProbabilisticBatch:
        self.vendor.fetch_called_with = {
            "symbol": symbol,
            "start": start,
            "end": end,
            "interval": interval,
            "vendor": vendor,
            "limit": limit,
        }
        return self.vendor.to_probabilistic_batch()


def _build_bars(symbol: str, vendor: str, start: datetime, count: int) -> Bars:
    bars = Bars(symbol=symbol, vendor=vendor, timezone="UTC")
    for idx in range(count):
        ts = start + timedelta(days=idx)
        bars.append(
            Bar(
                symbol=symbol,
                vendor=vendor,
                timestamp=ts,
                open=100 + idx,
                high=101 + idx,
                low=99 + idx,
                close=100 + idx,
                volume=1_000 + idx,
                timezone="UTC",
                source="historical",
            )
        )
    return bars


def _build_signals(
    symbol: str, vendor: str, start: datetime, count: int
) -> list[SignalFrame]:
    signals: list[SignalFrame] = []
    for idx in range(count):
        ts = start + timedelta(days=idx)
        signals.append(
            SignalFrame(
                symbol=symbol,
                vendor=vendor,
                timestamp=ts,
                price=100.0 + idx,
                volume=1_000 + idx,
                filtered_price=100.0 + idx * 0.5,
                velocity=0.1 * idx,
                uncertainty=0.02,
                butterworth_price=100.0 + idx * 0.4,
                ema_price=100.0 + idx * 0.3,
            )
        )
    return signals


def _build_regimes(symbol: str, start: datetime, count: int) -> list[RegimeSnapshot]:
    regimes: list[RegimeSnapshot] = []
    labels = ["trend_up", "sideways", "trend_down", "high_volatility", "uncertain"]
    for idx in range(count):
        ts = start + timedelta(days=idx)
        label = labels[idx % len(labels)]
        regimes.append(
            RegimeSnapshot(
                symbol=symbol,
                timestamp=ts,
                regime=label,
                volatility=0.01 * (idx + 1),
                uncertainty=0.02 * (idx + 1),
                momentum=0.001 * idx,
            )
        )
    return regimes


@pytest.mark.parametrize(
    "use_probabilistic, regime_aware", [(True, True), (True, False)]
)
def test_breakout_run_probabilistic_smoke(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    use_probabilistic: bool,
    regime_aware: bool,
):
    symbol = "AAPL"
    start_str = "2021-01-01"
    end_str = "2021-01-05"
    start_dt = datetime(2021, 1, 1, tzinfo=timezone.utc)

    dates = pd.date_range(start=start_str, end=end_str, freq="D")
    def fake_generate_signals(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        base = pd.DataFrame(
            {
                "open": df.get("open", df.get("Open")),
                "high": df.get("high", df.get("High")),
                "low": df.get("low", df.get("Low")),
                "close": df.get("close", df.get("Close")),
                "long_entry": [True] + [False] * (len(df) - 1),
                "long_exit": [False] * (len(df) - 1) + [True],
                "atr": np.full(len(df), 1.5),
                "atr_ok": True,
            },
            index=df.index,
        )
        return base

    fake_beta = _FakeBetaWinrate()
    engine_stub = _FakeBacktestEngine()

    bars = _build_bars(symbol, "hybrid", start_dt, len(dates))
    signals = _build_signals(symbol, "hybrid", start_dt, len(dates))
    regimes = _build_regimes(symbol, start_dt, len(dates))
    if regime_aware:
        regimes[-1] = RegimeSnapshot(
            symbol=symbol,
            timestamp=start_dt + timedelta(days=len(dates) - 1),
            regime="trend_down",
            volatility=0.05,
            uncertainty=0.08,
            momentum=-0.002,
        )

    vendor = _HybridVendor(bars=bars, signals=signals, regimes=regimes)

    def fake_market_data_dal_factory(*args: Any, **kwargs: Any):
        kwargs["vendor"] = vendor
        return _FakeMarketDataDAL(*args, **kwargs)

    monkeypatch.setenv("BACKTEST_NO_SAVE", "1")
    monkeypatch.setenv("BACKTEST_OUT_DIR", str(tmp_path))

    monkeypatch.setattr(
        "app.backtest.run_breakout.generate_signals", fake_generate_signals
    )
    monkeypatch.setattr("app.backtest.run_breakout.BetaWinrate", lambda: fake_beta)
    monkeypatch.setattr("app.backtest.run_breakout.backtest_long_only", engine_stub)
    monkeypatch.setattr(
        "app.backtest.run_breakout.bt_metrics.equity_stats",
        lambda equity, use_mtm=True: _FakeMetrics(),
    )
    monkeypatch.setattr(
        "app.backtest.run_breakout.MarketDataDAL", fake_market_data_dal_factory
    )

    breakout_run(
        symbol=symbol,
        start=start_str,
        end=end_str,
        params_kwargs={"lookback": 3},
        slippage_bps=1.0,
        fee_per_share=0.0,
        min_notional=50.0,
        debug=False,
        debug_signals=False,
        debug_entries=False,
        regime_aware_sizing=regime_aware,
        use_probabilistic=use_probabilistic,
        dal_vendor="hybrid",
        dal_interval="1Day",
        export_csv=None,
    )

    assert engine_stub.last_kwargs is not None, "Backtest engine did not receive call"
    risk_frac_used = engine_stub.last_kwargs["risk_frac"]

    base_risk = 0.01 * fake_beta.kelly_fraction() / fake_beta.fmax
    if use_probabilistic and regime_aware:
        expected_multiplier = 0.6 * 0.7  # trend_down scaling with uncertainty > 0.05
    else:
        expected_multiplier = 1.0
    assert pytest.approx(risk_frac_used, rel=1e-5) == base_risk * expected_multiplier

    if use_probabilistic:
        assert vendor.fetch_called_with is not None
