# Data Schemas

## Candles (per timeframe)
- ts: int64 (epoch ms)
- open, high, low, close: float
- volume: int64
- vwap: float (if available)
- spread_pct: float (quote-derived)
- session: enum {PRE, REG-AM, REG-MID, REG-PM, AFT}

## Features (joined on ts, symbol)
- ema_20/50/200, rsi_14, atr_14, bb_width, roc_5, macd_hist
- rvol, range_z, micro_liquidity proxies
- regime_trend, regime_vol

## Labels
- y_bin: {0,1} (next-k return > 0)
- y_reg: float (next-k return)
- horizon_k: int (bars)

## Trades (DB: postgres public.trades)
- trade_id (uuid pk), symbol, side, qty, entry_px, exit_px, sl_px, tp_px
- opened_at, closed_at (timestamptz), session_open, session_close
- slippage_bp, spread_entry_pct, mae, mfe, pnl, r_multiple, rule_hits (jsonb)

## Orders (DB: postgres public.orders)
- order_id (uuid pk), client_order_id, symbol, side, type, qty, limit_px, stop_px, status, created_at, updated_at, session

## Journal (DB: postgres public.journal)
- id (uuid pk), trade_id (fk), note_ts, reasoning (text), ai_summary (text), tags (text[])

### Initial DDL
```sql
CREATE TABLE IF NOT EXISTS trades (
  trade_id uuid PRIMARY KEY,
  symbol text NOT NULL,
  side text NOT NULL,
  qty numeric NOT NULL,
  entry_px numeric NOT NULL,
  exit_px numeric,
  sl_px numeric,
  tp_px numeric,
  opened_at timestamptz NOT NULL,
  closed_at timestamptz,
  session_open text NOT NULL,
  session_close text,
  slippage_bp numeric,
  spread_entry_pct numeric,
  mae numeric,
  mfe numeric,
  pnl numeric,
  r_multiple numeric,
  rule_hits jsonb DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS orders (
  order_id uuid PRIMARY KEY,
  client_order_id text,
  symbol text NOT NULL,
  side text NOT NULL,
  type text NOT NULL,
  qty numeric NOT NULL,
  limit_px numeric,
  stop_px numeric,
  status text NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz,
  session text NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
  id uuid PRIMARY KEY,
  trade_id uuid REFERENCES trades(trade_id) ON DELETE CASCADE,
  note_ts timestamptz NOT NULL,
  reasoning text,
  ai_summary text,
  tags text[]
);