from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from pydantic.fields import AliasChoices
from sqlalchemy import Column, Integer, String, Float, JSON, DateTime, text
from app.adapters.db.postgres import Base


class Bar(BaseModel):
    """
    A Pydantic model for a single bar of price data.

    Attributes:
        o (float): The open price.
        h (float): The high price.
        low (float): The low price.
        c (float): The close price.
        v (int): The volume.
        t (Optional[str]): The timestamp.
        S (Optional[str]): The symbol.
        T (Optional[str]): The alternative symbol.
    """

    o: float = Field(0.0, validation_alias=AliasChoices("o", "open"))
    h: float = Field(0.0, validation_alias=AliasChoices("h", "high"))
    low: float = Field(0.0, validation_alias=AliasChoices("l", "lo", "low"))
    c: float = Field(0.0, validation_alias=AliasChoices("c", "close"))
    v: int = Field(0, validation_alias=AliasChoices("v", "volume"))
    t: Optional[str] = None
    S: Optional[str] = None
    T: Optional[str] = None

    @property
    def mid(self) -> float:
        """The midpoint of the bar's range."""
        return (self.h + self.low) / 2.0

    @property
    def body(self) -> float:
        """The absolute body size of the bar."""
        return abs(self.c - self.o)

    @property
    def range(self) -> float:
        """The high-low range of the bar."""
        return self.h - self.low

    @property
    def ts_utc(self) -> Optional[datetime]:
        """The timestamp of the bar in UTC."""
        if not self.t:
            return None
        try:
            iso = self.t.replace("Z", "+00:00")
            return datetime.fromisoformat(iso).astimezone(timezone.utc)
        except Exception:
            return None

    def __repr__(self) -> str:
        return f"Bar(o={self.o:.2f}, h={self.h:.2f}, low={self.low:.2f}, c={self.c:.2f}, v={self.v})"

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
        "alias_generator": to_camel,
    }


class OHLCV(BaseModel):
    """
    A Pydantic model for OHLCV data.

    Attributes:
        o (float): The open price.
        h (float): The high price.
        low (float): The low price.
        c (float): The close price.
        v (int): The volume.
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
    """
    A Pydantic model for a market snapshot.

    Attributes:
        latestTrade (Dict[str, Any]): The latest trade data.
        latestQuote (Dict[str, Any]): The latest quote data.
        dailyBar (Dict[str, Any]): The daily bar data.
        prevDailyBar (Dict[str, Any]): The previous daily bar data.
    """
    latestTrade: Dict[str, Any] = Field(default_factory=dict)
    latestQuote: Dict[str, Any] = Field(default_factory=dict)
    dailyBar: Dict[str, Any] = Field(default_factory=dict)
    prevDailyBar: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


class WatchlistItem(BaseModel):
    """
    A Pydantic model for a watchlist item.

    Attributes:
        symbol (str): The symbol of the item.
        last (float): The last price of the item.
        price_source (str): The source of the price.
        ohlcv (Bar): The OHLCV data for the item.
        metadata (Dict[str, Any]): A dictionary of metadata.
    """
    symbol: str
    last: float = 0.0
    price_source: str = "none"
    ohlcv: Bar = Field(default_factory=Bar)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def __repr__(self) -> str:
        return f"WatchlistItem(symbol={self.symbol}, last={self.last:.2f}, src={self.price_source})"

    model_config = {"extra": "ignore"}


class Watchlist(BaseModel):
    """
    A Pydantic model for a watchlist.

    Attributes:
        session (str): The trading session.
        asof_utc (str): The timestamp of the watchlist.
        items (List[WatchlistItem]): A list of watchlist items.
    """
    session: str
    asof_utc: str
    items: List[WatchlistItem] = Field(default_factory=list)

    @property
    def count(self) -> int:
        """The number of items in the watchlist."""
        return len(self.items)

    model_config = {"extra": "ignore"}

class Trade(Base):
    """
    A SQLAlchemy model for a trade.

    Attributes:
        id (int): The trade ID.
        symbol (str): The symbol of the trade.
        entry_price (float): The entry price of the trade.
        exit_price (float): The exit price of the trade.
        quantity (float): The quantity of the trade.
        pnl (float): The profit and loss of the trade.
        meta (JSON): A JSON object for metadata.
        created_at (DateTime): The timestamp of the trade.
    """
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float)
    quantity = Column(Float)
    pnl = Column(Float)
    meta = Column(JSON)
    created_at = Column(DateTime, server_default=text("NOW()"))
