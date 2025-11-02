from __future__ import annotations

"""
Postgres engine/session helpers with safe DSN building, minimal logging, and
resilient health checks. Prefers DATABASE_URL when set; otherwise builds from
individual PG* env vars with sslmode=require by default (works for Azure FS).
"""

import os
import time
from typing import Optional
from urllib.parse import quote_plus

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from app.utils import env as ENV

Base = declarative_base()

# ----------------------------------------------------------------------------
# DSN helpers
# ----------------------------------------------------------------------------


def get_db_url() -> Optional[str]:
    """
    Retrieves the database DSN from environment variables.

    Returns:
        Optional[str]: The database DSN if found, otherwise None.
    """
    # Prefer production DSN; fall back to TEST_DATABASE_URL (e.g., CI) if present
    return os.getenv("DATABASE_URL") or os.getenv("TEST_DATABASE_URL")


def _dsn_from_env() -> Optional[str]:
    """
    DEPRECATED: Use get_db_url() instead.
    Retrieves the database DSN from environment variables.
    """
    # Prefer production DSN; fall back to TEST_DATABASE_URL (e.g., CI) if present
    return os.getenv("DATABASE_URL") or os.getenv("TEST_DATABASE_URL")


def _sanitize_dsn(dsn: str) -> str:
    """
    Redacts the password from a DSN string for safe logging.

    Args:
        dsn (str): The DSN string.

    Returns:
        str: The sanitized DSN string.
    """
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
    """
    Creates a new SQLAlchemy Engine.

    Args:
        dsn (Optional[str]): The database DSN.
        pool_size (int): The connection pool size.
        max_overflow (int): The maximum number of connections to allow in the pool.

    Returns:
        Optional[Engine]: A new Engine instance, or None if no DSN is configured.
    """
    dsn = dsn or get_db_url()
    if not dsn:
        try:
            logger.warning("[postgres] no DSN in env; engine not created")
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
        logger.info("[postgres] engine created dsn={}", _sanitize_dsn(dsn))
    except Exception:
        pass
    return eng


def get_engine() -> Optional[Engine]:
    """
    Retrieves a singleton SQLAlchemy Engine instance.

    Returns:
        Optional[Engine]: The singleton Engine instance, or None if not configured.
    """
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = make_engine()
    return _ENGINE


def make_session_factory(engine: Optional[Engine] = None) -> Optional[sessionmaker]:
    """
    Creates a new SQLAlchemy sessionmaker.

    Args:
        engine (Optional[Engine]): The Engine to bind the sessionmaker to.

    Returns:
        Optional[sessionmaker]: A new sessionmaker instance, or None if not configured.
    """
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
    """
    Retrieves a new SQLAlchemy Session.

    Returns:
        Session: A new Session instance.

    Raises:
        RuntimeError: If the database engine is not configured.
    """
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
    """
    Pings the database to check for connectivity.

    Args:
        engine (Optional[Engine]): The Engine to use for the ping.
        timeout_sec (float): The timeout in seconds for the ping.
        retries (int): The number of times to retry the ping.
        backoff (float): The backoff factor for retries.

    Returns:
        bool: True if the ping is successful, False otherwise.
    """

    eng = engine or get_engine()
    if eng is None:
        logger.warning("[postgres] ping: no engine available (no DSN)")
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
            logger.warning(
                "[postgres] ping failed (attempt {}/{}): {}", attempts, retries + 1, e
            )
            if attempts > retries:
                return False
            time.sleep(backoff * attempts)

@contextlib.contextmanager
def get_db():
    """
    A generator function that yields a new SQLAlchemy Session.

    Yields:
        Session: A new Session instance.

    Raises:
        RuntimeError: If the database engine is not configured.
    """
    factory = make_session_factory()
    if factory is None:
        raise RuntimeError("Database engine not configured (no DSN in env)")
    db = factory()
    try:
        yield db
    finally:
        db.close()
