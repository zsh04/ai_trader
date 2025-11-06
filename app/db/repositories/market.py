from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import models


class MarketRepository:
    """Persistence helpers for market metadata and price snapshots."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # Symbols -----------------------------------------------------------------
    def upsert_symbols(self, payloads: Sequence[Mapping[str, object]]) -> None:
        """Insert or update symbol metadata in bulk."""
        if not payloads:
            return
        stmt = insert(models.Symbol).values(payloads)
        update_cols = {
            "name": stmt.excluded.name,
            "asset_class": stmt.excluded.asset_class,
            "primary_exchange": stmt.excluded.primary_exchange,
            "currency": stmt.excluded.currency,
            "status": stmt.excluded.status,
            "figi": stmt.excluded.figi,
            "isin": stmt.excluded.isin,
            "attributes": stmt.excluded.attributes,
            "updated_at": stmt.excluded.updated_at,
        }
        self.session.execute(
            stmt.on_conflict_do_update(index_elements=["symbol"], set_=update_cols)
        )

    def fetch_symbols(self, symbols: Iterable[str]) -> list[models.Symbol]:
        sym_list = list({sym.upper() for sym in symbols if sym})
        if not sym_list:
            return []
        stmt = (
            select(models.Symbol)
            .where(models.Symbol.symbol.in_(sym_list))
            .order_by(models.Symbol.symbol)
        )
        return list(self.session.scalars(stmt))

    # Price snapshots ---------------------------------------------------------
    def record_price_snapshots(
        self,
        snapshots: Sequence[Mapping[str, object]],
    ) -> None:
        """Persist vendor-normalised price snapshots."""
        if not snapshots:
            return
        normalized: list[dict[str, object]] = []
        ingest_ts = datetime.now(timezone.utc)
        for snap in snapshots:
            data = dict(snap)
            data.setdefault("ingestion_ts", ingest_ts)
            normalized.append(data)
        stmt = insert(models.PriceSnapshot).values(normalized)
        self.session.execute(stmt)

    def latest_price_snapshots(
        self, symbols: Iterable[str], vendor_priority: Sequence[str]
    ) -> dict[str, models.PriceSnapshot]:
        """Return most recent snapshot per symbol favouring vendor priority order."""
        sym_list = list({sym.upper() for sym in symbols if sym})
        if not sym_list:
            return {}
        stmt = (
            select(models.PriceSnapshot)
            .where(models.PriceSnapshot.symbol.in_(sym_list))
            .order_by(models.PriceSnapshot.symbol, models.PriceSnapshot.ts_utc.desc())
        )
        grouped: dict[str, dict[str, models.PriceSnapshot]] = defaultdict(dict)
        for row in self.session.scalars(stmt):
            grouped[row.symbol][row.vendor] = row

        result: dict[str, models.PriceSnapshot] = {}
        for symbol, vendor_map in grouped.items():
            for vendor in vendor_priority:
                if vendor in vendor_map:
                    result[symbol] = vendor_map[vendor]
                    break
            else:
                # fallback to most recent vendor
                result[symbol] = next(
                    iter(
                        sorted(
                            vendor_map.values(), key=lambda r: r.ts_utc, reverse=True
                        )
                    )
                )
        return result
