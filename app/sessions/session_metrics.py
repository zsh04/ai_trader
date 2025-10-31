from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping

PRE = "PRE"
REG_AM = "REG-AM"
REG_MID = "REG-MID"
REG_PM = "REG-PM"
AFT = "AFT"

SESSION_ORDER = (PRE, REG_AM, REG_MID, REG_PM, AFT)


@dataclass(slots=True)
class MetricEvent:
    """
    A data class for a single metric event.

    Attributes:
        session (str): The session the event occurred in.
        pnl (float): The profit and loss of the event.
        slippage_bp (float): The slippage in basis points.
        spread_pct (float): The spread in percentage points.
    """

    session: str
    pnl: float = 0.0
    slippage_bp: float = 0.0
    spread_pct: float = 0.0


@dataclass
class SessionMetrics:
    """
    A data class for collecting and summarizing session metrics.
    """

    buckets: Dict[str, List[MetricEvent]] = field(
        default_factory=lambda: {k: [] for k in SESSION_ORDER}
    )

    def record(self, ev: MetricEvent) -> None:
        """
        Records a single metric event.

        Args:
            ev (MetricEvent): The metric event to record.
        """
        self.buckets.setdefault(ev.session, []).append(ev)

    def record_many(self, events: Iterable[MetricEvent]) -> None:
        """
        Records multiple metric events.

        Args:
            events (Iterable[MetricEvent]): A list of metric events to record.
        """
        for ev in events:
            self.record(ev)

    def summary(self) -> Dict[str, Dict[str, float]]:
        """
        Summarizes the metrics for each session.

        Returns:
            Dict[str, Dict[str, float]]: A dictionary of session summaries.
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
        """
        Summarizes the metrics for all sessions.

        Returns:
            Dict[str, float]: A dictionary of overall summaries.
        """
        s = self.summary()
        total_trades = int(sum(v["trades"] for v in s.values()))
        total_pnl = float(sum(v["pnl"] for v in s.values()))
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

    def merge(self, other: "SessionMetrics") -> "SessionMetrics":
        """
        Merges another SessionMetrics object into this one.

        Args:
            other (SessionMetrics): The SessionMetrics object to merge.

        Returns:
            SessionMetrics: The merged SessionMetrics object.
        """
        for k, events in other.buckets.items():
            self.buckets.setdefault(k, []).extend(events)
        return self

    def to_dict(self) -> Dict[str, Mapping[str, float]]:
        """
        Converts the SessionMetrics object to a dictionary.

        Returns:
            Dict[str, Mapping[str, float]]: A dictionary representation of the SessionMetrics object.
        """
        data = self.summary()
        data["OVERALL"] = self.overall()
        return data

    def reset(self) -> None:
        """
        Resets the metrics.
        """
        for k in list(self.buckets.keys()):
            self.buckets[k].clear()
