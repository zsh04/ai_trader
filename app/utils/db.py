# app/utils/db.py
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from app.config import settings

_engine: Engine | None = None

def pg_engine() -> Engine:
    global _engine
    if _engine is None:
        url = (
            f"postgresql+psycopg2://{settings.pg_user}:{settings.pg_password}"
            f"@{settings.pg_host}:{settings.pg_port}/{settings.pg_db}"
        )
        if settings.pg_sslmode:
            url += f"?sslmode={settings.pg_sslmode}"
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
    return _engine