from __future__ import annotations

from typing import Any, Dict, List, Optional

from datetime import datetime, timezone

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from pydantic.fields import AliasChoices


# NOTE: We standardize on `low` for readability (avoid linter E741 on `l`).
#       We also accept multiple inbound aliases (e.g., "l", "lo", "low")
#       so providers with short keys still deserialize cleanly.


class Bar(BaseModel):
    """Unified bar record used across the app.

    Accepts common aliases from providers (Alpaca, Yahoo), but normalizes
    attribute names to short, consistent fields used in the codebase.
    """

    # Short canonical names used in the app
    o: float = Field(0.0, validation_alias=AliasChoices("o", "open"))
    h: float = Field(0.0, validation_alias=AliasChoices("h", "high"))
    low: float = Field(0.0, validation_alias=AliasChoices("l", "lo", "low"))
    c: float = Field(0.0, validation_alias=AliasChoices("c", "close"))
    v: int = Field(0, validation_alias=AliasChoices("v", "volume"))

    # Optional provider extras (ignored if missing)
    t: Optional[str] = None  # ISO timestamp if available
    S: Optional[str] = None  # Alpaca symbol field
    T: Optional[str] = None  # Alt symbol field

    # --- Computed helpers (not serialized) ---
    @property
    def mid(self) -> float:
        """Midpoint of the bar's range."""
        return (self.h + self.low) / 2.0

    @property
    def body(self) -> float:
        """Absolute body size |close - open|."""
        return abs(self.c - self.o)

    @property
    def range(self) -> float:
        """High-low range."""
        return self.h - self.low

    @property
    def ts_utc(self) -> Optional[datetime]:
        """Parse and normalize the provider timestamp `t` (if present) to UTC."""
        if not self.t:
            return None
        try:
            # Accept both '...Z' and explicit offsets
            iso = self.t.replace("Z", "+00:00")
            return datetime.fromisoformat(iso).astimezone(timezone.utc)
        except Exception:
            return None

    def __repr__(self) -> str:  # pragma: no cover - convenience for logs
        return f"Bar(o={self.o:.2f}, h={self.h:.2f}, low={self.low:.2f}, c={self.c:.2f}, v={self.v})"

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
        "alias_generator": to_camel,
    }


class OHLCV(BaseModel):
    """Kept for compatibility where a pure OHLCV container is needed.

    Mirrors Bar but without provider extras. Accepts the same inbound aliases.
    """

    o: float = Field(0.0, validation_alias=AliasChoices("o", "open"))
    h: float = Field(0.0, validation_alias=AliasChoices("h", "high"))
    low: float = Field(0.0, validation_alias=AliasChoices("l", "lo", "low"))
    c: float = Field(0.0, validation_alias=AliasChoices("c", "close"))
    v: int = Field(0, validation_alias=AliasChoices("v", "volume"))

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
        "alias_generator": to_camel,
    }


class Snapshot(BaseModel):
    # Provider snapshots are heterogeneous; keep as dicts but ignore extras.
    latestTrade: Dict[str, Any] = Field(default_factory=dict)
    latestQuote: Dict[str, Any] = Field(default_factory=dict)
    dailyBar: Dict[str, Any] = Field(default_factory=dict)
    prevDailyBar: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


class WatchlistItem(BaseModel):
    symbol: str
    last: float = 0.0
    price_source: str = "none"
    ohlcv: Bar = Field(default_factory=Bar)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def __repr__(self) -> str:  # pragma: no cover - convenience for logs
        return f"WatchlistItem(symbol={self.symbol}, last={self.last:.2f}, src={self.price_source})"

    model_config = {"extra": "ignore"}


class Watchlist(BaseModel):
    session: str
    asof_utc: str
    items: List[WatchlistItem] = Field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.items)

    model_config = {"extra": "ignore"}
