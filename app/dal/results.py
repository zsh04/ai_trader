from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from app.agent.probabilistic.regime import RegimeSnapshot
from app.dal.schemas import Bars, SignalFrame


@dataclass(slots=True)
class ProbabilisticBatch:
    """Container for synchronized bars, signal frames, and regime snapshots."""

    bars: Bars
    signals: List[SignalFrame]
    regimes: List[RegimeSnapshot]
    cache_paths: Dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class ProbabilisticStreamFrame:
    """Streaming probabilistic payload containing both signal and regime views."""

    signal: SignalFrame
    regime: RegimeSnapshot


__all__ = ["ProbabilisticBatch", "ProbabilisticStreamFrame"]
