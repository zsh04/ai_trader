from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass(slots=True)
class RouterRequest:
    symbol: str
    start: datetime
    end: Optional[datetime]
    strategy: str = "breakout"
    params: Dict[str, Any] = field(default_factory=dict)
    use_probabilistic: bool = True
    dal_vendor: str = "alpaca"
    dal_interval: str = "1Day"
    min_notional: float = 100.0
    max_notional: float = 5_000.0
    side: str = "buy"


@dataclass(slots=True)
class RouterContext:
    run_id: str = field(default_factory=lambda: uuid4().hex)
    manifest_root: Path = Path("artifacts/probabilistic/frames")
    jobs_output: Path = Path("artifacts/orchestration")
    publish_orders: bool = False
    execute_orders: bool = False
    offline_mode: bool = False
    strategy_overrides: Dict[str, Any] = field(default_factory=dict)
    max_latency_ms: int = 1_200
    fallback_to_breakout: bool = True
    kill_switch_notional: float = 10_000.0
    risk_agent_fraction: float = 0.5
    dal_backfill_days: int = 60
    alpaca_key: Optional[str] = None
    alpaca_secret: Optional[str] = None
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    tp_pct: float = 0.03
    sl_pct: float = 0.01


@dataclass(slots=True)
class RouterResult:
    run_id: str
    symbol: str
    strategy: str
    latency_ms: float
    order_intent: Optional[Dict[str, Any]]
    prob_frame_path: Optional[str]
    priors: Optional[Dict[str, Any]]
    events: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    fallback_reason: Optional[str] = None


def default_time_window(days: int = 60) -> tuple[datetime, datetime]:
    now = datetime.now(tz=UTC)
    return now - timedelta(days=days), now
