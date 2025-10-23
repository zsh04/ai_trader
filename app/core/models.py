from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class Bar(BaseModel):
    o: float = 0.0
    h: float = 0.0
    l: float = 0.0
    c: float = 0.0
    v: int = 0
    t: Optional[str] = None  # ISO timestamp if available
    S: Optional[str] = None  # Alpaca symbol field
    T: Optional[str] = None  # Alt symbol field

class Snapshot(BaseModel):
    latestTrade: Dict[str, Any] = Field(default_factory=dict)
    latestQuote: Dict[str, Any] = Field(default_factory=dict)
    dailyBar: Dict[str, Any] = Field(default_factory=dict)
    prevDailyBar: Dict[str, Any] = Field(default_factory=dict)

class WatchlistItem(BaseModel):
    symbol: str
    last: float = 0.0
    price_source: str = "none"
    ohlcv: Bar = Field(default_factory=Bar)

class Watchlist(BaseModel):
    session: str
    asof_utc: str
    items: List[WatchlistItem] = Field(default_factory=list)