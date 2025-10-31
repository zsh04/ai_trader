# app/repositories/watchlist_index.py
from __future__ import annotations
import os
from typing import List, Optional, Tuple, Dict
from datetime import datetime, timezone
from loguru import logger

DDL = """
CREATE TABLE IF NOT EXISTS watchlist_index (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  bucket TEXT NOT NULL,
  asof_utc TIMESTAMPTZ NOT NULL,
  source TEXT NOT NULL,
  count INTEGER NOT NULL,
  tags TEXT[] NOT NULL DEFAULT '{}',
  blob_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS watchlist_index_bucket_asof ON watchlist_index(bucket, asof_utc DESC);
"""

def _pg():
    """
    Returns the psycopg2 module if available.

    Returns:
        The psycopg2 module or None.
    """
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return None
    try:
        import psycopg2
        return psycopg2
    except Exception as e:
        logger.warning("psycopg2 not installed; skipping index writes: {}", e)
        return None

def ensure_schema():
    """
    Ensures the database schema for the watchlist index exists.
    """
    pg = _pg()
    if not pg: return
    try:
        conn = pg.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(DDL)
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        logger.warning("watchlist_index schema ensure skipped: {}", e)

def insert_index(bucket: str, asof_utc: datetime, source: str, count: int, tags: List[str], blob_path: str):
    """
    Inserts a new record into the watchlist index.

    Args:
        bucket (str): The bucket name.
        asof_utc (datetime): The timestamp of the watchlist.
        source (str): The source of the watchlist.
        count (int): The number of symbols in the watchlist.
        tags (List[str]): A list of tags for the watchlist.
        blob_path (str): The path to the watchlist blob.
    """
    pg = _pg()
    if not pg: return
    sql = "INSERT INTO watchlist_index(bucket, asof_utc, source, count, tags, blob_path) VALUES (%s,%s,%s,%s,%s,%s)"
    try:
        conn = pg.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(sql, (bucket, asof_utc, source, count, tags, blob_path))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        logger.warning("watchlist_index insert skipped: {}", e)

def latest_for_bucket(bucket: str) -> Optional[Dict[str, object]]:
    """
    Retrieves the latest watchlist for a given bucket.

    Args:
        bucket (str): The bucket name.

    Returns:
        Optional[Dict[str, object]]: The latest watchlist, or None if not found.
    """
    pg = _pg()
    if not pg: return None
    sql = "SELECT bucket, asof_utc, source, count, tags, blob_path FROM watchlist_index WHERE bucket=%s ORDER BY asof_utc DESC LIMIT 1"
    try:
        conn = pg.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
        cur.execute(sql, (bucket,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row: return None
        return {"bucket": row[0], "asof_utc": row[1].astimezone(timezone.utc).isoformat(), "source": row[2], "count": row[3], "tags": row[4], "blob_path": row[5]}
    except Exception as e:
        logger.warning("watchlist_index latest query failed: {}", e)
        return None
