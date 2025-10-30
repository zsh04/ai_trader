# app/domain/watchlist_models.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional

@dataclass
class WatchlistDoc:
  bucket: str
  asof_utc: datetime
  source: str
  symbols: List[str]
  tags: List[str] = field(default_factory=list)
  meta: Dict[str, object] = field(default_factory=dict)

  def to_json(self) -> Dict[str, object]:
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