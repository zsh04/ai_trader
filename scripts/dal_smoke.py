#!/usr/bin/env python3
"""Live DAL smoke test covering multiple vendors."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from loguru import logger

from app.dal.manager import MarketDataDAL

DEFAULT_CHECKS: Sequence[tuple[str, str, str, int]] = (
    ("alpaca", "AAPL", "1Day", 120),
    ("alphavantage", "MSFT", "15Min", 5),
    ("alphavantage_eod", "SPY", "1Day", 400),
    ("yahoo", "QQQ", "1Day", 400),
    ("twelvedata", "NVDA", "1Day", 120),
    ("finnhub", "AAPL", "1Day", 60),
)


@dataclass
class SmokeResult:
    vendor: str
    symbol: str
    interval: str
    lookback_days: int
    status: str
    bars: int = 0
    signals: int = 0
    regimes: int = 0
    cache_paths: Dict[str, str] | None = None
    error: Optional[str] = None


def _run_single_check(
    dal: MarketDataDAL,
    vendor: str,
    symbol: str,
    interval: str,
    lookback_days: int,
) -> SmokeResult:
    window_start = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    try:
        batch = dal.fetch_bars(
            symbol=symbol,
            start=window_start,
            end=None,
            interval=interval,
            vendor=vendor,
        )
        return SmokeResult(
            vendor=vendor,
            symbol=symbol,
            interval=interval,
            lookback_days=lookback_days,
            status="ok",
            bars=len(batch.bars.data),
            signals=len(batch.signals),
            regimes=len(batch.regimes),
            cache_paths={k: str(v) for k, v in (batch.cache_paths or {}).items()},
        )
    except Exception as exc:  # pragma: no cover - network failures are expected
        logger.warning(
            "DAL smoke failed vendor=%s symbol=%s interval=%s error=%s",
            vendor,
            symbol,
            interval,
            exc,
        )
        return SmokeResult(
            vendor=vendor,
            symbol=symbol,
            interval=interval,
            lookback_days=lookback_days,
            status="error",
            error=str(exc),
        )


def _write_report(results: Iterable[SmokeResult], output_dir: Path) -> Path:
    report_dir = output_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = report_dir / f"dal_smoke_{ts}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": [asdict(res) for res in results],
    }
    path.write_text(json.dumps(payload, indent=2))
    logger.info("[dal-smoke] wrote report -> %s", path)
    return path


def _parse_checks(
    arg_checks: Optional[List[str]],
) -> Sequence[tuple[str, str, str, int]]:
    if not arg_checks:
        return DEFAULT_CHECKS
    parsed = []
    for entry in arg_checks:
        try:
            vendor, symbol, interval, lookback = entry.split(":", maxsplit=3)
            parsed.append((vendor, symbol, interval, int(lookback)))
        except ValueError as exc:
            raise ValueError(
                f"Invalid check format '{entry}'. Expected vendor:symbol:interval:lookbackDays"
            ) from exc
    return parsed


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exercise MarketDataDAL vendors end-to-end."
    )
    parser.add_argument(
        "--check",
        action="append",
        dest="checks",
        help="Custom vendor spec vendor:symbol:interval:lookbackDays (can repeat).",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/ops/dal_smoke",
        help="Directory to store JSON reports (default: artifacts/ops/dal_smoke).",
    )
    args = parser.parse_args(argv)
    checks = _parse_checks(args.checks)
    dal = MarketDataDAL(enable_postgres_metadata=False)

    results: List[SmokeResult] = []
    for vendor, symbol, interval, lookback in checks:
        logger.info(
            "[dal-smoke] running vendor=%s symbol=%s interval=%s lookback=%s",
            vendor,
            symbol,
            interval,
            lookback,
        )
        results.append(_run_single_check(dal, vendor, symbol, interval, lookback))

    failures = [res for res in results if res.status != "ok"]
    report_path = _write_report(results, Path(args.output_dir))
    logger.info(
        "[dal-smoke] completed checks=%s failures=%s report=%s",
        len(results),
        len(failures),
        report_path,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
