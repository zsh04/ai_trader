# app/sources

This folder contains data source adapters for watchlist ingestion.

Contract:

- Each adapter exposes `get_symbols(*, max_symbols: int | None = None) -> list[str]`
- Returned symbols must be uppercase strings and deduplicated.

Backends:

- `textlist_source` - shared parser for env / text backends
- `signal_text`, `discord_text` - env/text stubs
- `alpha_source` - Alpha Vantage listing/quote helpers (see `app/services/watchlist_sources.py`)
- `finnhub_source` - Finnhub symbol/quote helpers (same module)
