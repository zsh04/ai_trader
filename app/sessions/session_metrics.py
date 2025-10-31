from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping

# Canonical session labels we use across the app
PRE = "PRE"
REG_AM = "REG-AM"
REG_MID = "REG-MID"
REG_PM = "REG-PM"
AFT = "AFT"

SESSION_ORDER = (PRE, REG_AM, REG_MID, REG_PM, AFT)


@dataclass(slots=True)
class MetricEvent:
    """One trade/decision metric captured for a session bucket.

    Attributes
    ----------
    session: str
        One of SESSION_ORDER, e.g. "REG-AM".
    pnl: float
        Realized P&L contribution for the event (base currency units).
    slippage_bp: float
        Slippage in basis points (positive = adverse).
    spread_pct: float
        Inside spread paid as percent of price (0.001 = 0.1%).
    """

    session: str
    pnl: float = 0.0
    slippage_bp: float = 0.0
    spread_pct: float = 0.0


@dataclass
class SessionMetrics:
    """Collects per-session execution metrics and summarizes them.

    The structure is intentionally stdlib-only so it can be used in
    backtests and live services without extra dependencies.
    """

    buckets: Dict[str, List[MetricEvent]] = field(
        default_factory=lambda: {k: [] for k in SESSION_ORDER}
    )

    # --- Recording -------------------------------------------------------
    def record(self, ev: MetricEvent) -> None:
        """Record a single event, auto-creating a bucket if needed."""
        self.buckets.setdefault(ev.session, []).append(ev)

    def record_many(self, events: Iterable[MetricEvent]) -> None:
        for ev in events:
            self.record(ev)

    # --- Summaries -------------------------------------------------------
    def summary(self) -> Dict[str, Dict[str, float]]:
        """Return per-session summary with trades, pnl, and averages.

        Output schema per session key:
            {
                "trades": int,
                "pnl": float,
                "avg_slippage_bp": float,
                "avg_spread_pct": float,
            }
        """
        out: Dict[str, Dict[str, float]] = {}
        for k in SESSION_ORDER:
            events = self.buckets.get(k, [])
            if not events:
                out[k] = {
                    "trades": 0,
                    "pnl": 0.0,
                    "avg_slippage_bp": 0.0,
                    "avg_spread_pct": 0.0,
                }
                continue

            trades = len(events)
            pnl = sum(e.pnl for e in events)
            avg_slip = sum(e.slippage_bp for e in events) / trades
            avg_spread = sum(e.spread_pct for e in events) / trades
            out[k] = {
                "trades": trades,
                "pnl": pnl,
                "avg_slippage_bp": avg_slip,
                "avg_spread_pct": avg_spread,
            }
        return out

    def overall(self) -> Dict[str, float]:
        """Aggregate totals across all sessions."""
        s = self.summary()
        total_trades = int(sum(v["trades"] for v in s.values()))
        total_pnl = float(sum(v["pnl"] for v in s.values()))
        # Weighted averages (by trade count) for slippage/spread
        if total_trades:
            w_slip = (
                sum(v["avg_slippage_bp"] * v["trades"] for v in s.values())
                / total_trades
            )
            w_spread = (
                sum(v["avg_spread_pct"] * v["trades"] for v in s.values())
                / total_trades
            )
        else:
            w_slip = 0.0
            w_spread = 0.0
        return {
            "trades": total_trades,
            "pnl": total_pnl,
            "avg_slippage_bp": w_slip,
            "avg_spread_pct": w_spread,
        }

    # --- Utilities -------------------------------------------------------
    def merge(self, other: "SessionMetrics") -> "SessionMetrics":
        """Merge another metrics object into this one (in-place)."""
        for k, events in other.buckets.items():
            self.buckets.setdefault(k, []).extend(events)
        return self

    def to_dict(self) -> Dict[str, Mapping[str, float]]:
        """Convenience: full payload with per-session and overall."""
        data = self.summary()
        data["OVERALL"] = self.overall()
        return data

    def reset(self) -> None:
        for k in list(self.buckets.keys()):
            self.buckets[k].clear()
