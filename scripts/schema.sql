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