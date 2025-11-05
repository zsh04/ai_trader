

```mermaid
%% PHASE 4 — LIVE EXECUTION (ai_trader)
%% Covers runtime topology, order routing, risk & compliance,
%% fault-tolerance, observability, and runbook.

%% ------------------------------------------------------------
%% 1) Runtime Topology / Data Flow
%% ------------------------------------------------------------
flowchart LR
  subgraph TG["User Interfaces"]
    TG1[/Telegram Bot/]
    PNL[/Read-only API/]
  end

  subgraph APP["ai_trader App Service (FastAPI + Workers)"]
    API[[REST Routes
    /health /watchlist /orders
    /positions /metrics]]
    RT[Real-time Loop
    (symbol tickers,
    signal → order)]
    RM[Risk Manager
    (exposure, caps,
    pre-trade checks)]
    OR[Order Router
    (Alpaca REST/WebSocket)]
    OMS[OMS Cache
    (orders, fills,
    positions, PnL)]
    SCHED[Cron/Jobs
    (rebalance, EOD,
    rollovers)]
  end

  subgraph DATA["Market Data"]
    A1[(Alpaca Data API v2
    snapshots/bars)]
    YF[(Yahoo fallback)]
  end

  subgraph BROKER["Broker"]
    B1[(Alpaca Trading API
    paper/live accounts)]
  end

  subgraph STOR["Storage & State"]
    PG[(PostgreSQL traderdata
    orders, fills, runs)]
    BLOB[(Blob/Files: logs,
    reports, artifacts)]
    CFG[(.env / KeyVault
    app settings)]
  end

  TG1 -->|/ping /help /watchlist| API
  PNL --> API
  API --> RT
  RT --> RM --> OR --> B1
  RT --> |read| A1
  RT --> |fallback| YF
  OR --> |persist events| PG
  OMS --> |periodic snapshots| PG
  API --> |read positions/metrics| PG
  SCHED --> RT
  CFG --> APP
  APP --> BLOB

%% ------------------------------------------------------------
%% 2) Sequence — Signal to Fill (happy path)
%% ------------------------------------------------------------
sequenceDiagram
  autonumber
  participant STR as Strategy Loop
  participant RM as Risk Manager
  participant OR as Order Router
  participant BR as Broker (Alpaca)
  participant OMS as OMS Cache
  participant DB as PostgreSQL

  STR->>STR: on_tick(bars)
  STR-->>STR: signal: long_entry(symbol, qty_hint)
  STR->>RM: pre_trade_checks(signal)
  RM-->>STR: ok + sized_qty
  STR->>OR: send_order(symbol, side, qty, type=LMT, px)
  OR->>BR: POST /v2/orders
  BR-->>OR: order_id, status=accepted
  OR->>OMS: upsert(order)
  OMS->>DB: INSERT orders
  BR-->>OR: fill update (stream)
  OR->>OMS: apply_fill(order_id, price, qty)
  OMS->>DB: INSERT fills; UPDATE positions
  OMS-->>STR: position snapshot + PnL

%% ------------------------------------------------------------
%% 3) Pre-Trade Risk & Compliance Gate
%% ------------------------------------------------------------
flowchart TB
  SIG([Signal]) --> POS{Current exposure <
  limit per symbol & portfolio?}
  POS -- no --> BLK([Block order + alert])
  POS -- yes --> LIQ{Sufficient buying power?
  (account cash, margin)}
  LIQ -- no --> BLK
  LIQ -- yes --> HALT{Market open &
  symbol tradable?}
  HALT -- no --> QD([queue/defer])
  HALT -- yes --> SAN([sanitize qty/px,
  round lots, min_notional]) --> OK([Allow order])

%% ------------------------------------------------------------
%% 4) Resiliency / Fault-Tolerance
%% ------------------------------------------------------------
stateDiagram-v2
  [*] --> Healthy
  Healthy --> DataDegraded: A1 4xx/5xx or stale > N sec
  DataDegraded --> Fallback: switch to Yahoo
  Fallback --> Healthy: data restored
  Healthy --> BrokerDegraded: trading 4xx/5xx, throttling
  BrokerDegraded --> RetryBackoff: exp-backoff + jitter
  RetryBackoff --> CircuitOpen: consecutive failures > K
  CircuitOpen --> SafeMode: stop new orders,
  close-risky positions optional
  SafeMode --> Healthy: manual reset or auto after cool-down

%% ------------------------------------------------------------
%% 5) Observability Pack
%% ------------------------------------------------------------
flowchart LR
  subgraph LOGS[Logs]
    APPLOG>App logs]
    WEBLOG>HTTP access logs]
  end
  subgraph MET[Metrics]
    M1[(latency_ms: data/broker)]
    M2[(orders_sent, fills, rejects)]
    M3[(exposure_pct, cash, BP)]
    M4[(pnl_intraday, dd)]
  end
  subgraph ALR[Alerts]
    AERR([Error rate spike])
    AEXPO([Exposure > cap])
    ADATA([Data stale > N sec])
    ABROK([Order rejects > T])
  end

  APPLOG & WEBLOG --> BLOB
  MET --> API
  API --> TG1
  MET --> ALR
  ALR --> TG1

### Watchlist Command Routing
- Telegram `/watchlist` requests flow through the FastAPI router, which resolves sources using positional syntax `auto|alpha|finnhub|textlist|twelvedata [scanner] [limit] [sort]`.
- `auto` maps to Finviz by default and will fall back to TextList when the Finviz adapter cannot produce symbols; manual `textlist` requests bypass external dependencies entirely.
- Responses reuse the shared watchlist resolver, guaranteeing consistent symbol sets across Telegram, REST `/tasks/watchlist`, and scheduled jobs.

%% ------------------------------------------------------------
%% 6) Deployment & Promotion Flow
%% ------------------------------------------------------------
flowchart LR
  DEV[(Commit main)] --> CI[CI: lint+tests]
  CI --> PCK[Build artifact]
  PCK --> STAGE[(Azure Staging Slot)]
  STAGE --> PROBE[/Live probes
  /health/live, smoke/]
  PROBE --> CAN{Manual check OK?}
  CAN -- yes --> SWAP[[Slot Swap → Prod]]
  CAN -- no --> ROLLBACK[[Stay on prod,
  fix & redeploy]]

%% ------------------------------------------------------------
%% 7) Runbook — Common Ops
%% ------------------------------------------------------------
mindmap
  root((Runbook))
    Data
      (Check data feed env: ALPACA_DATA_FEED)
      (401 from Alpaca → verify keys & plan)
      (Fallback Yahoo auto; disable via flag if needed)
    Broker
      (Paper vs Live keys separated via slots)
      (Throttling → exp backoff + circuit)
      (Rejects → inspect payload, symbol halts)
    App
      (Tail logs: az webapp log tail)
      (Scale out workers if backlog)
      (SafeMode toggle via env)
    DB
      (Connectivity: /health/db)
      (Slow writes → batch/queue)
    Telegram
      (Webhook secret mismatch → resetWebhook)
      (/help, /watchlist from commands map)

%% ------------------------------------------------------------
%% 8) Gantt — Phase 4 Delivery
%% ------------------------------------------------------------
gantt
  title PHASE 4 — Execution Delivery Plan
  dateFormat  YYYY-MM-DD
  axisFormat  %b %d

  section Hardening
  Risk gate & caps                 :active, r1, 2025-10-28, 2d
  Circuit breaker / fallback       :        r2, after r1, 2d
  Observability pack               :        r3, after r2, 2d

  section Broker & Routing
  Order router (limit/mkt/stop)    :done,   b1, 2025-10-24, 2025-10-27
  Position & OMS cache             :active, b2, 2025-10-28, 2d

  section Delivery
  Staging slot + smoke             :done,   d1, 2025-10-27, 1d
  Slot swap & rollback plan        :        d2, 2025-10-29, 1d
  Runbook + SOP docs               :        d3, after d2, 1d
```
