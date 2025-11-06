# Changelog

## Unreleased

### Added

- Daily Alpha Vantage vendor (`alphavantage_eod`) with automatic fallback to Yahoo and Twelve Data when rate-limited.
- Documentation refresh covering the Market Data DAL, secrets mapping, and watchlist sources.

### Changed

- Migrated legacy `app/providers` usage to DAL vendors (Alpaca, Alpha Vantage, Finnhub, Twelve Data) and removed the old package.
- Finnhub vendor now returns daily quotes via the `/quote` endpoint until intraday access is enabled.
- `.env.example` and Key Vault guidance now list all active market data keys.
- README architecture map updated for the new module layout and Streamlit dashboard.

### Removed

- Deprecated `docs/reference/CHANGELOG.md` in favour of this canonical changelog.
