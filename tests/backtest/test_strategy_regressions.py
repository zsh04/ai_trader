from __future__ import annotations

from dataclasses import asdict, dataclass
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
from app.probability.pipeline import join_probabilistic_features
from app.strats.breakout import BreakoutParams
from app.strats.breakout import generate_signals as breakout_signals
from app.strats.mean_reversion import generate_signals as mean_reversion_signals
from app.strats.momentum import generate_signals as momentum_signals
from app.strats.params import MeanReversionParams, MomentumParams


class _RecordingEngine:
    def __init__(self) -> None:
        self.last_kwargs: Dict[str, Any] | None = None

    def __call__(self, **kwargs: Any) -> Dict[str, Any]:
        self.last_kwargs = kwargs
        length = len(kwargs["df"])
        index = pd.date_range("2021-01-01", periods=length, freq="D")
        equity = pd.Series(
            np.linspace(100.0, 100.0 + length, length), index=index, name="equity"
        )
        return {"equity": equity, "trades": []}


class _FixedBeta:
    def __init__(self) -> None:
        self.fmax = 1.0

    def kelly_fraction(self) -> float:
        return 0.1


@dataclass
class _FakeMetrics:
    start: datetime = datetime(2021, 1, 1, tzinfo=timezone.utc)
    end: datetime = datetime(2021, 1, 2, tzinfo=timezone.utc)
    periods: int = 1
    cagr: float = 0.0
    total_return: float = 0.0
    vol: float = 0.0
    sharpe: float = 1.0
    sortino: float = 1.0
    max_drawdown: float = 0.0
    max_dd_len: int = 0
    mar: float = 0.0


class _FakeMarketDataDAL:
    def __init__(self, batch: ProbabilisticBatch) -> None:
        self.batch = batch

    def fetch_bars(self, *args: Any, **kwargs: Any) -> ProbabilisticBatch:
        return self.batch


def _build_prob_batch(
    symbol: str, closes: List[float], *, vendor: str = "stub"
) -> ProbabilisticBatch:
    bars = Bars(symbol=symbol, vendor=vendor, timezone="UTC")
    signals: List[SignalFrame] = []
    regimes: List[RegimeSnapshot] = []
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    for idx, close in enumerate(closes):
        ts = start + timedelta(days=idx)
        bars.append(
            Bar(
                symbol=symbol,
                vendor=vendor,
                timestamp=ts,
                open=close - 0.5,
                high=close + 0.5,
                low=close - 1.0,
                close=close,
                volume=1_000 + idx,
                timezone="UTC",
                source="stub",
            )
        )
        signals.append(
            SignalFrame(
                symbol=symbol,
                vendor=vendor,
                timestamp=ts,
                price=close,
                volume=1_000 + idx,
                filtered_price=close - 0.2,
                velocity=0.05 * (idx + 1),
                uncertainty=0.01 * (idx + 1),
                butterworth_price=close - 0.1,
                ema_price=close - 0.15,
            )
        )
        regimes.append(
            RegimeSnapshot(
                symbol=symbol,
                timestamp=ts,
                regime="trend_up" if idx % 2 == 0 else "calm",
                volatility=0.01 * (idx + 1),
                uncertainty=0.02 * (idx + 1),
                momentum=0.001 * idx,
            )
        )
    return ProbabilisticBatch(
        bars=bars, signals=signals, regimes=regimes, cache_paths={}
    )


@pytest.fixture(autouse=True)
def _patch_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.backtest.run_breakout.bt_metrics.equity_stats",
        lambda equity, use_mtm=True: _FakeMetrics(),
    )
    monkeypatch.setattr("app.backtest.run_breakout.BetaWinrate", lambda: _FixedBeta())


def _setup_common(
    monkeypatch: pytest.MonkeyPatch, batch: ProbabilisticBatch, tmp_path: Path
) -> _RecordingEngine:
    fake_dal = _FakeMarketDataDAL(batch)
    monkeypatch.setattr(
        "app.backtest.run_breakout.MarketDataDAL", lambda *args, **kwargs: fake_dal
    )
    engine = _RecordingEngine()
    monkeypatch.setattr("app.backtest.run_breakout.backtest_long_only", engine)
    monkeypatch.setenv("BACKTEST_PROB_FRAME_DIR", str(tmp_path / "frames"))
    monkeypatch.setenv("BACKTEST_OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("BACKTEST_NO_SAVE", "1")
    return engine


def _expected_entry_events(
    sig: pd.DataFrame, *, strategy: str, params_obj: Any
) -> pd.Series:
    entry_state = sig.get("long_entry", pd.Series(False, index=sig.index)).astype(bool)
    entry_event = entry_state & ~entry_state.shift(1, fill_value=False)
    if strategy == "breakout":
        enter_samebar = bool(getattr(params_obj, "enter_on_break_bar", False))
    else:
        enter_samebar = bool(getattr(params_obj, "enter_on_signal_bar", False))
    if not enter_samebar:
        entry_event = entry_event.shift(1, fill_value=False)
    entry_event = entry_event.reindex(sig.index, fill_value=False)
    return entry_event.astype(bool)


def test_breakout_regression_entry_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    closes = [10, 11, 12, 11.5, 13, 14]
    batch = _build_prob_batch("AAPL", closes)
    engine = _setup_common(monkeypatch, batch, tmp_path)

    df = batch.bars.to_dataframe()
    enriched = join_probabilistic_features(
        df, signals=batch.signals, regimes=batch.regimes
    )
    params = {"lookback": 2, "atr_len": 2, "atr_mult": 1.5}
    params_obj = BreakoutParams(**params)
    sig = breakout_signals(enriched, asdict(params_obj))
    expected_events = _expected_entry_events(
        sig, strategy="breakout", params_obj=params_obj
    )

    result = breakout_run(
        symbol="AAPL",
        start="2021-01-01",
        end="2021-01-06",
        params_kwargs=params,
        strategy="breakout",
        use_probabilistic=True,
        dal_vendor="stub",
        dal_interval="1Day",
    )

    assert engine.last_kwargs is not None
    actual = engine.last_kwargs["entry"].astype(bool)
    expected_aligned = expected_events.reindex(actual.index).fillna(False).astype(bool)
    pd.testing.assert_series_equal(actual, expected_aligned)
    assert Path(result["prob_frame_path"]).exists()


def test_momentum_regression_probabilistic_join(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    closes = [100, 101, 103, 104, 105, 106]
    batch = _build_prob_batch("MSFT", closes)
    engine = _setup_common(monkeypatch, batch, tmp_path)

    df = batch.bars.to_dataframe()
    enriched = join_probabilistic_features(
        df, signals=batch.signals, regimes=batch.regimes
    )
    params = {"roc_lookback": 1, "ema_fast": 2, "rank_window": 3, "atr_len": 2}
    params_obj = MomentumParams(**params)
    sig = momentum_signals(enriched, asdict(params_obj))
    expected_events = _expected_entry_events(
        sig, strategy="momentum", params_obj=params_obj
    )

    result = breakout_run(
        symbol="MSFT",
        start="2021-01-01",
        end="2021-01-06",
        params_kwargs=params,
        strategy="momentum",
        use_probabilistic=True,
        dal_vendor="stub",
        dal_interval="1Day",
    )

    assert engine.last_kwargs is not None
    actual = engine.last_kwargs["entry"].astype(bool)
    expected_aligned = expected_events.reindex(actual.index).fillna(False).astype(bool)
    pd.testing.assert_series_equal(actual, expected_aligned)
    assert Path(result["prob_frame_path"]).exists()


def test_mean_reversion_regression_probabilistic_join(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    closes = [50, 49, 48, 47, 48, 49, 50]
    batch = _build_prob_batch("QQQ", closes)
    engine = _setup_common(monkeypatch, batch, tmp_path)

    df = batch.bars.to_dataframe()
    enriched = join_probabilistic_features(
        df, signals=batch.signals, regimes=batch.regimes
    )
    params = {"lookback": 3, "z_entry": -0.5, "z_exit": -0.1, "atr_len": 2}
    params_obj = MeanReversionParams(**params)
    sig = mean_reversion_signals(enriched, asdict(params_obj))
    expected_events = _expected_entry_events(
        sig, strategy="mean_reversion", params_obj=params_obj
    )

    result = breakout_run(
        symbol="QQQ",
        start="2021-01-01",
        end="2021-01-07",
        params_kwargs=params,
        strategy="mean_reversion",
        use_probabilistic=True,
        dal_vendor="stub",
        dal_interval="1Day",
    )

    assert engine.last_kwargs is not None
    actual = engine.last_kwargs["entry"].astype(bool)
    expected_aligned = expected_events.reindex(actual.index).fillna(False).astype(bool)
    pd.testing.assert_series_equal(actual, expected_aligned)
    assert Path(result["prob_frame_path"]).exists()
