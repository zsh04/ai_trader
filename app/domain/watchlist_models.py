# app/domain/watchlist_models.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional

@dataclass
class WatchlistDoc:
  """
  A data class for a watchlist document.

  Attributes:
      bucket (str): The bucket the watchlist belongs to.
      asof_utc (datetime): The timestamp of the watchlist.
      source (str): The source of the watchlist.
      symbols (List[str]): A list of symbols in the watchlist.
      tags (List[str]): A list of tags for the watchlist.
      meta (Dict[str, object]): A dictionary of metadata.
  """
  bucket: str
  asof_utc: datetime
  source: str
  symbols: List[str]
  tags: List[str] = field(default_factory=list)
  meta: Dict[str, object] = field(default_factory=dict)

  def to_json(self) -> Dict[str, object]:
      """
      Converts the watchlist document to a JSON-serializable dictionary.

      Returns:
          Dict[str, object]: A dictionary representation of the watchlist document.
      """
      return {
          "bucket": self.bucket,
          "asof_utc": self.asof_utc.replace(tzinfo=timezone.utc).isoformat(),
          "source": self.source,
          "symbols": self.symbols,
          "tags": self.tags,
          "meta": self.meta,
      }

  @staticmethod
  def from_json(data: Dict[str, object]) -> "WatchlistDoc":
      """
      Creates a WatchlistDoc from a JSON-serializable dictionary.

      Args:
          data (Dict[str, object]): A dictionary representation of the watchlist document.

      Returns:
          WatchlistDoc: A WatchlistDoc object.
      """
      from datetime import datetime
      asof = data.get("asof_utc")
      if isinstance(asof, str):
          asof_dt = datetime.fromisoformat(asof.replace("Z", "+00:00"))
      else:
          asof_dt = datetime.now(timezone.utc)
      return WatchlistDoc(
          bucket=str(data.get("bucket") or "default"),
          asof_utc=asof_dt,
          source=str(data.get("source") or "unknown"),
          symbols=list(data.get("symbols") or []),
          tags=list(data.get("tags") or []),
          meta=dict(data.get("meta") or {}),
      )
