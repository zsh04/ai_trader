# app/domain/watchlist_repo.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.adapters.storage.azure_blob import WatchlistBlobStore
from app.domain.watchlist_models import WatchlistDoc
from app.repositories import watchlist_index as idx

logger = logging.getLogger(__name__)


class WatchlistRepo:
    def __init__(self):
        self.store = WatchlistBlobStore()
        idx.ensure_schema()

    @staticmethod
    def _sanitize_bucket(bucket: str) -> str:
        return "".join(
            ch for ch in bucket.strip().lower() if ch.isalnum() or ch in ("-", "_")
        )

    def save(
        self,
        bucket: str,
        symbols: List[str],
        *,
        source: str,
        tags: List[str] | None = None,
        meta: Dict[str, object] | None = None,
    ) -> WatchlistDoc:
        b = self._sanitize_bucket(bucket) or "default"
        asof = datetime.now(timezone.utc)
        wl = WatchlistDoc(
            bucket=b,
            asof_utc=asof,
            source=source,
            symbols=list(
                dict.fromkeys([s.upper().strip() for s in symbols if s and s.strip()])
            ),
        )
        if tags:
            wl.tags = list(
                dict.fromkeys([t.strip().lower() for t in tags if t and t.strip()])
            )
        if meta:
            wl.meta = dict(meta)
        blob_path = self.store.write_json(b, asof, wl.to_json())
        try:
            idx.insert_index(b, asof, wl.source, len(wl.symbols), wl.tags, blob_path)
        except Exception as e:
            logger.warning("watchlist index insert failed: %s", e)
        return wl

    def latest(self, bucket: str) -> Optional[WatchlistDoc]:
        b = self._sanitize_bucket(bucket) or "default"
        data = self.store.read_latest(b)
        return WatchlistDoc.from_json(data) if data else None

    def nearest_on(self, bucket: str, yyyymmdd: str) -> Optional[WatchlistDoc]:
        b = self._sanitize_bucket(bucket) or "default"
        data = self.store.read_nearest_date(b, yyyymmdd)
        return WatchlistDoc.from_json(data) if data else None
