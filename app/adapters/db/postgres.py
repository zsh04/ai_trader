from __future__ import annotations
import os
from typing import Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from app.utils import env as ENV

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
    pwd  = ENV.PGPASSWORD or os.getenv("PGPASSWORD", "")
    host = ENV.PGHOST or os.getenv("PGHOST", "localhost")
    port = int(ENV.PGPORT or os.getenv("PGPORT", 5432))
    db   = ENV.PGDATABASE or os.getenv("PGDATABASE", "postgres")
    ssl  = ENV.PGSSLMODE or os.getenv("PGSSLMODE", "require")

    user_q = quote_plus(user)
    pwd_q  = quote_plus(pwd)

    # Example: postgresql+psycopg2://user:pass@host:5432/db?sslmode=require
    return f"postgresql+psycopg2://{user_q}:{pwd_q}@{host}:{port}/{db}?sslmode={ssl}"


# ----------------------------------------------------------------------------
# Engine / sessions (cached)
# ----------------------------------------------------------------------------

_ENGINE: Optional[Engine] = None
_SESSION_FACTORY: Optional[sessionmaker] = None

def make_engine(dsn: Optional[str] = None, pool_size: int = 5, max_overflow: int = 5) -> Engine:
    """Create a new Engine (uncached). Prefer `get_engine()` for a singleton."""
    dsn = dsn or _dsn_from_env()
    return create_engine(
        dsn,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )


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

def ping(engine: Optional[Engine] = None) -> bool:
    try:
        eng = engine or get_engine()
        with eng.begin() as cx:
            cx.execute(text("SELECT 1"))
        return True
    except Exception:
        return False