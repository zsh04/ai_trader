# app/domain/watchlist_repo.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional, Dict
from loguru import logger

from app.domain.watchlist_models import WatchlistDoc
from app.adapters.storage.azure_blob import WatchlistBlobStore
from app.repositories import watchlist_index as idx

class WatchlistRepo:
    """
    A repository for managing watchlists.
    """
    def __init__(self):
        """
        Initializes the WatchlistRepo.
        """
        self.store = WatchlistBlobStore()
        idx.ensure_schema()

    @staticmethod
    def _sanitize_bucket(bucket: str) -> str:
        """
        Sanitizes a bucket name.

        Args:
            bucket (str): The bucket name to sanitize.

        Returns:
            str: The sanitized bucket name.
        """
        return "".join(ch for ch in bucket.strip().lower() if ch.isalnum() or ch in ("-", "_"))

    def save(self, bucket: str, symbols: List[str], *, source: str, tags: List[str] | None = None, meta: Dict[str, object] | None = None) -> WatchlistDoc:
        """
        Saves a watchlist.

        Args:
            bucket (str): The bucket to save the watchlist to.
            symbols (List[str]): A list of symbols to save.
            source (str): The source of the watchlist.
            tags (List[str] | None): A list of tags for the watchlist.
            meta (Dict[str, object] | None): A dictionary of metadata.

        Returns:
            WatchlistDoc: The saved watchlist document.
        """
        b = self._sanitize_bucket(bucket) or "default"
        asof = datetime.now(timezone.utc)
        wl = WatchlistDoc(bucket=b, asof_utc=asof, source=source, symbols=list(dict.fromkeys([s.upper().strip() for s in symbols if s and s.strip()])))
        if tags: wl.tags = list(dict.fromkeys([t.strip().lower() for t in tags if t and t.strip()]))
        if meta: wl.meta = dict(meta)
        blob_path = self.store.write_json(b, asof, wl.to_json())
        try:
            idx.insert_index(b, asof, wl.source, len(wl.symbols), wl.tags, blob_path)
        except Exception as e:
            logger.warning("watchlist index insert failed: {}", e)
        return wl

    def latest(self, bucket: str) -> Optional[WatchlistDoc]:
        """
        Retrieves the latest watchlist from a bucket.

        Args:
            bucket (str): The bucket to retrieve the watchlist from.

        Returns:
            Optional[WatchlistDoc]: The latest watchlist document, or None if not found.
        """
        b = self._sanitize_bucket(bucket) or "default"
        data = self.store.read_latest(b)
        return WatchlistDoc.from_json(data) if data else None

    def nearest_on(self, bucket: str, yyyymmdd: str) -> Optional[WatchlistDoc]:
        """
        Retrieves the nearest watchlist from a bucket on a given date.

        Args:
            bucket (str): The bucket to retrieve the watchlist from.
            yyyymmdd (str): The date in YYYYMMDD format.

        Returns:
            Optional[WatchlistDoc]: The nearest watchlist document, or None if not found.
        """
        b = self._sanitize_bucket(bucket) or "default"
        data = self.store.read_nearest_date(b, yyyymmdd)
        return WatchlistDoc.from_json(data) if data else None
