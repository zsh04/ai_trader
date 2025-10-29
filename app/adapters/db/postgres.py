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
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from app.utils import env as ENV

Base = declarative_base()

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
log = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# DSN helpers
# ----------------------------------------------------------------------------


def _dsn_from_env() -> Optional[str]:
    # Prefer production DSN; fall back to TEST_DATABASE_URL (e.g., CI) if present
    return os.getenv("DATABASE_URL") or os.getenv("TEST_DATABASE_URL")


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


def make_engine(
    dsn: Optional[str] = None, pool_size: int = 5, max_overflow: int = 5
) -> Optional[Engine]:
    """Create a new Engine (uncached). Prefer `get_engine()` for a singleton.

    Returns None when no DSN is configured so callers can degrade gracefully.
    """
    dsn = dsn or _dsn_from_env()
    if not dsn:
        try:
            log.warning("[postgres] no DSN in env; engine not created")
        except Exception:
            pass
        return None
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


def get_engine() -> Optional[Engine]:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = make_engine()
    return _ENGINE


def make_session_factory(engine: Optional[Engine] = None) -> Optional[sessionmaker]:
    global _SESSION_FACTORY
    eng = engine if engine is not None else get_engine()
    if eng is None:
        return None
    if _SESSION_FACTORY is None or (
        engine is not None and _SESSION_FACTORY.kw.get("bind") is not eng
    ):
        _SESSION_FACTORY = sessionmaker(
            bind=eng, expire_on_commit=False, autoflush=False, future=True
        )
    return _SESSION_FACTORY


def get_session() -> Session:
    factory = make_session_factory()
    if factory is None:
        raise RuntimeError("Database engine not configured (no DSN in env)")
    return factory()


# ----------------------------------------------------------------------------
# Health / diagnostics
# ----------------------------------------------------------------------------


def ping(
    engine: Optional[Engine] = None,
    timeout_sec: float = 2.0,
    retries: int = 0,
    backoff: float = 0.75,
) -> bool:
    """Try a lightweight query with optional retries.

    For Postgres we also set a per-statement timeout for the connection where possible.
    """
    eng = engine or get_engine()
    if eng is None:
        log.warning("[postgres] ping: no engine available (no DSN)")
        return False

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
            log.warning(
                "[postgres] ping failed (attempt %s/%s): %s", attempts, retries + 1, e
            )
            if attempts > retries:
                return False
            time.sleep(backoff * attempts)

def get_db():
    factory = make_session_factory()
    if factory is None:
        raise RuntimeError("Database engine not configured (no DSN in env)")
    db = factory()
    try:
        yield db
    finally:
        db.close()
