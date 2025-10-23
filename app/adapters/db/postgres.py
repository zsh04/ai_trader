from __future__ import annotations
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def make_engine(dsn: str, pool_size: int = 5, max_overflow: int = 5):
    return create_engine(
        dsn,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )

def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)