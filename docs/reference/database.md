---
title: "Database Overview"
doc_type: reference
audience: intermediate
product_area: data
last_verified: 2025-11-06
toc: true
---

# Database Overview

## Purpose

Summarize how Azure Database for PostgreSQL Flexible Server is organized for AI Trader: schemas, critical tables, and operational considerations.

## Deployment profile

| Property | Value |
|----------|-------|
| Service tier | Flexible Server (Standard_B1ms) |
| Storage | 32 GB, auto-grow enabled |
| Networking | VNet integrated + private DNS; SSL enforced |
| Backups | PITR enabled, 7-day retention |

## Logical schemas

| Schema | Contents |
|--------|----------|
| `market` | Raw vendor metadata, symbol registry |
| `signals` | Probabilistic outputs, regime labels |
| `orders` | Order intents, acks, fills |
| `risk` | Guardrail evaluations, Kelly sizing snapshots |
| `backtest` | Sweep configs, metrics, artifacts index |

## Key tables

- `market.symbols (id, symbol, vendor, metadata JSONB)`
- `signals.frames (symbol, ts, regime, features JSONB)`
- `orders.executions (order_id, broker_id, status, fills JSONB)`
- `risk.kelly_caps (ts, symbol, kelly_fraction, reason)`
- `backtest.runs (id, strat, params JSONB, metrics JSONB, artifact_uri)`

## Ops checklist

1. Apply migrations via `alembic upgrade head` (CI dry-run writes SQL with `DATABASE_URL=sqlite://`).
2. Production migrations run against Azure Postgres using Managed Identity credentials stored in Key Vault.
3. Monitor `pg_stat_activity` and `pg_bloat` weekly; vacuum tables with heavy JSON updates.

## See also

- [Database Architecture](./database-architecture.md)
- [Secrets](./secrets.md)
- [How-to: managed identity](../howto/operations/managed-identity.md)
