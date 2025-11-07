---
title: "Database Architecture"
doc_type: reference
audience: intermediate
product_area: data
last_verified: 2025-11-06
toc: true
---

# Database Architecture

## Storage topology
- **Relational (Postgres/Timescale):** orders, fills, positions, runs, metrics
- **Files (Parquet/Delta):** OHLCV, features, backtests
- **Cache (Redis):** online features, queues

## ER diagram
```mermaid
classDiagram
  class Order { uuid id; string symbol; enum side; float qty; float price_intent; time created_at; text meta }
  class Fill { uuid id; uuid order_id; float price; float qty; time ts }
  class Position { string symbol; float qty; float avg_price; time updated_at }
  Order "1" --> "*" Fill : has
```

## Indexing & partitions
- Time partitions on `fills.ts`
- B-tree on `orders(symbol, created_at)`
- Table TTL/retention policy

## Backup & restore
- Daily logical backups + weekly snapshots
- PITR window (e.g., 7 days). Restore-tested quarterly

## Migration policy
- Forward-only migrations; idempotent backfills

## See also
- [Data Models](./data-models.md)
- [Operations runbook](../howto/operations/runbook.md)
- [Architecture core runtime](../explanations/architecture/core-runtime.md)
