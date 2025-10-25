from __future__ import annotations
"""
Postgres engine/session helpers with safe DSN building, minimal logging, and
resilient health checks. Prefers DATABASE_URL when set; otherwise builds from
individual PG* env vars with sslmode=require by default (works for Azure FS).
"""

import logging
import os
import time
from typing import Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.utils import env as ENV

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
log = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# DSN helpers
# ----------------------------------------------------------------------------


def _dsn_from_env() -> str:
    """Build a SQLAlchemy DSN from env. Prefer DATABASE_URL if present.

    Supports Azure Flexible Server by defaulting sslmode=require.
    """
    if ENV.DATABASE_URL:
        return ENV.DATABASE_URL

    user = ENV.PGUSER or os.getenv("PGUSER", "")
    pwd = ENV.PGPASSWORD or os.getenv("PGPASSWORD", "")
    host = ENV.PGHOST or os.getenv("PGHOST", "localhost")
    port = int(ENV.PGPORT or os.getenv("PGPORT", 5432))
    db = ENV.PGDATABASE or os.getenv("PGDATABASE", "postgres")
    ssl = ENV.PGSSLMODE or os.getenv("PGSSLMODE", "require")

    user_q = quote_plus(user)
    pwd_q = quote_plus(pwd)

    # Example: postgresql+psycopg2://user:pass@host:5432/db?sslmode=require
    return f"postgresql+psycopg2://{user_q}:{pwd_q}@{host}:{port}/{db}?sslmode={ssl}"


def _sanitize_dsn(dsn: str) -> str:
    """Redact password when logging DSN."""
    try:
        # naive redaction between ":" (after scheme//user) and "@"
        if "@" in dsn and "://" in dsn:
            scheme_user, rest = dsn.split("://", 1)
            if ":" in rest and "@" in rest:
                user_part, tail = rest.split("@", 1)
                if ":" in user_part:
                    user_only = user_part.split(":", 1)[0]
                    return f"{scheme_user}://{user_only}:***@{tail}"
        return dsn
    except Exception:
        return dsn


# ----------------------------------------------------------------------------
# Engine / sessions (cached)
# ----------------------------------------------------------------------------

_ENGINE: Optional[Engine] = None
_SESSION_FACTORY: Optional[sessionmaker] = None


def make_engine(dsn: Optional[str] = None, pool_size: int = 5, max_overflow: int = 5) -> Engine:
    """Create a new Engine (uncached). Prefer `get_engine()` for a singleton."""
    dsn = dsn or _dsn_from_env()
    eng = create_engine(
        dsn,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )
    try:
        log.info("[postgres] engine created dsn=%s", _sanitize_dsn(dsn))
    except Exception:
        pass
    return eng


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = make_engine()
    return _ENGINE


def make_session_factory(engine: Optional[Engine] = None) -> sessionmaker:
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None or (engine is not None and _SESSION_FACTORY.kw.get("bind") is not engine):
        eng = engine or get_engine()
        _SESSION_FACTORY = sessionmaker(bind=eng, expire_on_commit=False, autoflush=False, future=True)
    return _SESSION_FACTORY


def get_session() -> Session:
    """Convenience: get a Session from the cached factory."""
    return make_session_factory()()


# ----------------------------------------------------------------------------
# Health / diagnostics
# ----------------------------------------------------------------------------


def ping(engine: Optional[Engine] = None, timeout_sec: float = 2.0, retries: int = 0, backoff: float = 0.75) -> bool:
    """Try a lightweight query with optional retries.

    For Postgres we also set a per-statement timeout for the connection where possible.
    """
    eng = engine or get_engine()

    attempts = 0
    while True:
        attempts += 1
        try:
            with eng.begin() as cx:
                # Best-effort: set local statement timeout (milliseconds)
                try:
                    ms = int(max(timeout_sec, 0) * 1000)
                    cx.execute(text(f"SET LOCAL statement_timeout = {ms}"))
                except Exception:
                    pass
                cx.execute(text("SELECT 1"))
            return True
        except Exception as e:
            log.warning("[postgres] ping failed (attempt %s/%s): %s", attempts, retries + 1, e)
            if attempts > retries:
                return False
            time.sleep(backoff * attempts)
