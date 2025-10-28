-- scripts/schema.sql
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

create table if not exists watchlist_log (
  id uuid primary key default gen_random_uuid(),
  as_of_utc timestamptz not null,
  blob_path text not null,
  count int not null,
  kind text not null check (kind in ('PRE','REG','AFT'))
);
-- scripts/schema.sql
-- Baseline schema for AI Trader (watchlist + audit)

-- Extensions
create extension if not exists "pgcrypto";
create extension if not exists "uuid-ossp";

-- Session flag:
-- PRE = premarket, REG = regular session, AFT = after-hours

create table if not exists watchlist_log (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  as_of_utc timestamptz not null,
  session text not null check (session in ('PRE','REG','AFT')),
  source text not null default 'auto',
  title text,
  blob_path text,
  count integer not null,
  notes text,
  unique (as_of_utc, session, source)
);

create index if not exists ix_watchlist_log_created_at on watchlist_log (created_at desc);
create index if not exists ix_watchlist_log_asof_session on watchlist_log (as_of_utc desc, session);

create table if not exists watchlist_item (
  id uuid primary key default gen_random_uuid(),
  log_id uuid not null references watchlist_log(id) on delete cascade,
  symbol text not null,
  rank integer,
  last numeric(18,6),
  price_source text,
  meta jsonb not null default '{}'::jsonb,
  ohlcv jsonb not null default '{}'::jsonb,
  unique (log_id, symbol)
);

create index if not exists ix_watchlist_item_log_id on watchlist_item (log_id);
create index if not exists ix_watchlist_item_symbol on watchlist_item (symbol);
create index if not exists ix_watchlist_item_meta_gin on watchlist_item using gin (meta);
create index if not exists ix_watchlist_item_ohlcv_gin on watchlist_item using gin (ohlcv);

-- Optional: lightweight audit for Telegram webhook events
create table if not exists telegram_event (
  id uuid primary key default gen_random_uuid(),
  received_at timestamptz not null default now(),
  chat_id text,
  user_id text,
  command text,
  raw jsonb not null
);

create index if not exists ix_telegram_event_received_at on telegram_event (received_at desc);
create index if not exists ix_telegram_event_command on telegram_event (command);