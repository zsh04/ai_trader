"""Database package exposing SQLAlchemy base metadata and model imports."""

from __future__ import annotations

from app.adapters.db.postgres import Base, metadata  # re-export for convenience

# Import models so Alembic/SQLAlchemy register them when this package is loaded.
# Individual modules may import selectively to avoid circular dependencies.
from . import models  # noqa: F401

__all__ = ["Base", "metadata"]
