# app/repositories/watchlist_index.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import text

from app.adapters.db.postgres import get_db

logger = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS watchlist_index (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  bucket TEXT NOT NULL,
  asof_utc TIMESTAMPTZ NOT NULL,
  source TEXT NOT NULL,
  count INTEGER NOT NULL,
  tags TEXT[] NOT NULL DEFAULT '{}'::text[],
  blob_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS watchlist_index_bucket_asof ON watchlist_index(bucket, asof_utc DESC);
"""


def ensure_schema():
    try:
        with get_db() as db:
            db.execute(text(DDL))
            db.commit()
    except Exception as e:
        logger.warning("watchlist_index schema ensure skipped: %s", e)


def insert_index(
    bucket: str,
    asof_utc: datetime,
    source: str,
    count: int,
    tags: List[str],
    blob_path: str,
):
    sql = text(
        "INSERT INTO watchlist_index(bucket, asof_utc, source, count, tags, blob_path) "
        "VALUES (:bucket, :asof_utc, :source, :count, :tags, :blob_path)"
    )
    try:
        with get_db() as db:
            db.execute(
                sql,
                {
                    "bucket": bucket,
                    "asof_utc": asof_utc,
                    "source": source,
                    "count": count,
                    "tags": tags,
                    "blob_path": blob_path,
                },
            )
            db.commit()
    except Exception as e:
        logger.warning("watchlist_index insert skipped: %s", e)


def latest_for_bucket(bucket: str) -> Optional[Dict[str, object]]:
    sql = text(
        "SELECT bucket, asof_utc, source, count, tags, blob_path FROM watchlist_index "
        "WHERE bucket=:bucket ORDER BY asof_utc DESC LIMIT 1"
    )
    try:
        with get_db() as db:
            result = db.execute(sql, {"bucket": bucket}).fetchone()
        if not result:
            return None
        row = result._mapping
        return {
            "bucket": row["bucket"],
            "asof_utc": row["asof_utc"].astimezone(timezone.utc).isoformat(),
            "source": row["source"],
            "count": row["count"],
            "tags": row["tags"],
            "blob_path": row["blob_path"],
        }
    except Exception as e:
        logger.warning("watchlist_index latest query failed: %s", e)
        return None
