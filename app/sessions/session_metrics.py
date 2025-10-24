from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class MetricEvent:
    session: str
    pnl: float = 0.0
    slippage_bp: float = 0.0
    spread_pct: float = 0.0


@dataclass
class SessionMetrics:
    buckets: Dict[str, List[MetricEvent]] = field(
        default_factory=lambda: {
            "PRE": [],
            "REG-AM": [],
            "REG-MID": [],
            "REG-PM": [],
            "AFT": [],
        }
    )

    def record(self, ev: MetricEvent):
        if ev.session in self.buckets:
            self.buckets[ev.session].append(ev)

    def summary(self):
        out = {}
        for k, v in self.buckets.items():
            if not v:
                out[k] = {"trades": 0, "pnl": 0.0}
            else:
                out[k] = {"trades": len(v), "pnl": sum(e.pnl for e in v)}
        return out
