%% PHASE 3 — BACKTESTING (ai_trader)
%% This Mermaid bundle captures the architecture, data flows, class/ER maps,
%% execution sequences, parameter sweeps, parallelization, and delivery plan.

%% ------------------------------------------------------------
%% 1) Topology / Data Flow (high level)
%% ------------------------------------------------------------
flowchart LR
  subgraph EXT["External Providers"]
    MKT[(Market Data APIs\n(Alpaca, Yahoo, etc.))]
  end

  subgraph STG["Storage"]
    PQ[(Parquet OHLCV\ns3/azure/blob/local)]
    PG[(PostgreSQL\n(traderdata))]
    CFG[(Config YAML / .env)]
  end

  subgraph BT["Backtest Engine"]
    DL[DataLoader\n(windowing,resampling,adjustments)]
    STRAT[Strategy Runner\n(signals, params)]
    RISK[Risk Manager\n(position sizing,\nstop, take-profit)]
    BRK[BrokerSim\n(fills, slippage,\nfees, partials)]
    PTF[Portfolio & PnL\n(equity curve,\nexposure, drawdown)]
    MTRX[Metrics & Reports\n(Sharpe, Sortino,\nWinRate, MaxDD)]
  end

  subgraph IO["I/O Surfaces"]
    CLI[[CLI / Make / pytest]]
    API[[/backtest routes\n(Phase 4)]]
    RPT[(Artifacts & Reports\nHTML/CSV/JSON)]
  end

  MKT -->|historical bars| PQ
  DL --> STRAT --> RISK --> BRK --> PTF --> MTRX --> RPT
  CFG --> DL
  CFG --> STRAT
  PQ --> DL
  PG <--> MTRX
  CLI --> DL
  CLI --> STRAT
  API --> DL
  RPT -->|optional persist| PG

%% ------------------------------------------------------------
%% 2) Sequence — single backtest run
%% ------------------------------------------------------------
sequenceDiagram
  autonumber
  actor U as User/CI
  participant CLI as CLI/Runner
  participant DL as DataLoader
  participant STR as Strategy
  participant RISK as RiskMgr
  participant BRK as BrokerSim
  participant PTF as Portfolio
  participant M as Metrics/Reports

  U->>CLI: backtest --symbols AAPL,MSFT --start 2020-01-01 --params file.yaml
  CLI->>DL: load_bars(symbols, start, end, tz)
  DL-->>CLI: bars(DataFrame[OHLCV])
  loop for each bar t
    CLI->>STR: signals = on_bar(bars[t], state)
    STR-->>CLI: signals (long_entry/exit, size hints)
    CLI->>RISK: sized_orders = apply_rules(signals, exposure, stop/tp)
    RISK-->>CLI: orders (new/cancel/close)
    CLI->>BRK: simulate(orders, slippage, fees, latency)
    BRK-->>CLI: fills + updated positions
    CLI->>PTF: update(fills, prices[t])
    PTF-->>CLI: equity, drawdown, exposure
  end
  CLI->>M: compute(equity, trades, positions)
  M-->>U: report(Sharpe, Sortino, CAGR, MaxDD, charts)

%% ------------------------------------------------------------
%% 3) Class / ER model (core artifacts)
%% ------------------------------------------------------------
classDiagram
  class Bars {
    +symbol: str
    +df: DataFrame[datetime, open, high, low, close, volume]
    +tz: str
    +resample(tf) Bars
    +slice(start,end) Bars
  }

  class SignalFrame {
    +index: datetime
    +momentum: float
    +rank: float
    +long_entry: bool
    +long_exit: bool
  }

  class Order {
    +id: str
    +symbol: str
    +side: enum(Buy,Sell)
    +qty: float
    +type: enum(MKT,LMT,STP)
    +limit: float?
    +stop: float?
    +ts: datetime
  }

  class Fill {
    +order_id: str
    +symbol: str
    +qty: float
    +price: float
    +fee: float
    +slippage: float
    +ts: datetime
  }

  class Position {
    +symbol: str
    +qty: float
    +avg_price: float
    +unrealized_pnl: float
    +realized_pnl: float
    +update(fill) void
  }

  class Trade {
    +symbol: str
    +entry_ts: datetime
    +exit_ts: datetime
    +entry_px: float
    +exit_px: float
    +pnl: float
    +bars_held: int
  }

  class EquityCurve {
    +index: datetime
    +equity: float
    +drawdown: float
    +max_drawdown: float
  }

  class Metrics {
    +sharpe: float
    +sortino: float
    +win_rate: float
    +avg_win: float
    +avg_loss: float
    +cagr: float
    +max_dd: float
    +to_json() str
  }

  Bars --> SignalFrame : derive
  SignalFrame --> Order : generate
  Order --> Fill : simulated_by
  Fill --> Position : updates
  Position --> Trade : close_to_trade
  Position --> EquityCurve : mark_to_market
  EquityCurve --> Metrics : compute

%% ------------------------------------------------------------
%% 4) Parameter sweep & parallelization
%% ------------------------------------------------------------
flowchart TB
  subgraph DISPATCH["Param Dispatcher"]
    YAML[(params.yaml\n(grid/latin/random))]
    SPLIT[Generate param grid\n(p1 x p2 x ...)]
    Q[Task Queue]
  end

  subgraph EXEC["Execution Backends"]
    direction LR
    subgraph LOCAL["Local"]
      W1[Worker #1\nprocess]
      W2[Worker #2\nprocess]
      WN[Worker #N]
    end
    subgraph AZ["Azure Container Apps Jobs"]
      JW1[Job Run #1]
      JW2[Job Run #2]
      JWN[Job Run #N]
    end
  end

  subgraph SINK["Results Sink"]
    AR[(Artifacts: CSV/JSON/HTML)]
    DB[(PostgreSQL: runs, metrics)]
    SUM[Reducer: leaderboard,\nbest params]
  end

  YAML --> SPLIT --> Q
  Q -->|local| W1 & W2 & WN
  Q -->|azure| JW1 & JW2 & JWN
  W1 & W2 & WN --> AR & DB
  JW1 & JW2 & JWN --> AR & DB
  AR & DB --> SUM

%% ------------------------------------------------------------
%% 5) State model — BrokerSim/Position lifecycle
%% ------------------------------------------------------------
stateDiagram-v2
  [*] --> Flat
  Flat --> Long: Buy filled
  Flat --> Short: SellShort filled
  Long --> Flat: Sell to close
  Short --> Flat: Buy to cover
  Long --> Stopped: Stop-loss hit
  Long --> TP: Take-profit hit
  Short --> Stopped: Stop-loss hit
  Short --> TP: Take-profit hit
  Stopped --> Flat
  TP --> Flat

%% ------------------------------------------------------------
%% 6) Delivery Plan (Gantt)
%% ------------------------------------------------------------
gantt
  title PHASE 3 — Backtesting Delivery Plan
  dateFormat  YYYY-MM-DD
  axisFormat  %b %d

  section Core Engine
  Engine skeleton & broker sim        :done,    e1, 2025-10-20, 2025-10-24
  Risk sizing & stops                 :active,  e2, 2025-10-25, 3d
  Metrics pack + reports              :         e3, after e2, 3d

  section Data & Strategy
  DataLoader (parquet, PG, Yahoo)     :done,    d1, 2025-10-20, 2025-10-24
  Strategy adapter (momentum v1)      :active,  d2, 2025-10-25, 2d
  Warmup/window mgmt + resampling     :         d3, after d2, 2d

  section Scale-Out Sweeps
  CLI interface & params.yaml         :         s1, 2025-10-28, 1d
  Local parallel exec (multiproc)     :         s2, after s1, 2d
  ACA Jobs template (optional)        :         s3, after s2, 2d

  section Quality
  Test matrix (unit/integration)      :active,  q1, 2025-10-25, 5d
  Deterministic seeds & fixtures      :         q2, after q1, 2d
  CI wiring (GitHub Actions)          :done,    q3, 2025-10-27, 1d

  section Docs
  Developer guide + examples          :         doc1, 2025-10-28, 2d
  User guide (how-to run sweeps)      :         doc2, after doc1, 1d

%% ------------------------------------------------------------
%% 7) Notes / Checklist (mindmap)
%% ------------------------------------------------------------
mindmap
  root((Phase 3 Backtesting))
    Data
      (Consistent timezone)
      (Corporate actions policy)
      (NaN/Outlier handling)
    Strategy
      (Warmup bars & lookbacks)
      (Signal dtype: bool not object)
      (Cross-asset sync rules)
    BrokerSim
      (Slippage model: bps & queue)
      (Fees/commissions table)
      (Partial fills/latency)
    Risk
      (Max exposure %)
      (Position sizing formula)
      (Stop/TP configuration)
    Metrics
      (Equity curve + drawdown)
      (Sharpe/Sortino/CAGR/Hit rate)
      (Per-symbol stats)
    Reproducibility
      (Random seeds)
      (Run manifest in DB)
      (Hash of params & code rev)
    Scale
      (Chunking by symbol/date)
      (Parallel by symbol/grid)
      (Artifacts in blob/s3)