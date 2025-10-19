-- PostgreSQL schema for trades, orders, journal
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
