# 🧾 Changelog

## [0.1.1] — 2025-10-26

**Codename:** _“Codex Awakens”_  
Codex agents integrated, hygiene overhaul complete, and full system now stable across API, backtest, and Telegram layers.

---

### 🚀 New Features

- **Codex Integration:** Added `AGENTS.md` and connected VS Code Codex agents for automated patching, linting, and test scaffolding.
- **Health & Telemetry:**
  - `/health/live` and `/health/ready` endpoints operational.
  - Structured startup banner with version, environment, and timezone info.
- **Telegram Router:**
  - `/ping`, `/help`, `/watchlist` commands stabilized.
  - Mobile-safe parsing for smart quotes/dashes.
  - Unified error handling and user-friendly replies.
- **Utilities Layer:**
  - Added typed `ENV` dataclass with fallback defaults.
  - Introduced `normalize_quotes_and_dashes` and `parse_kv_flags` helpers.
  - Implemented `http_get` with retry/backoff and structured logging.
- **Backtest & Metrics:**
  - `breakout.py` refactored for robust signal generation and NaN-safe exits.
  - Metrics engine now includes **unrealized PnL** tracking.
  - CLI `run_breakout` hardened with debug mode and enhanced summaries.
- **Infrastructure:**
  - Split GitHub Actions into `ci.yml` (lint/test) and `deploy.yml` (Azure App Service).
  - Added `scripts/dev_helpers.sh` for local automation (`fmt`, `lint`, `test`, `ngrok`, `pm2`, `webhook`).
  - PM2 ecosystem file now supports log rotation and cleaner process management.
- **Tests & CI:**
  - Added smoke tests for `/health` and Telegram webhook.
  - Unit tests for `utils/` modules.
  - CI matrix expanded to Python 3.11 → 3.13.

---

### 🧹 Improvements

- Global code hygiene via **Ruff** + **Black** reformat.
- Added docstrings, type hints, and explicit return types across all layers.
- Consistent exception handling and logging schema.
- Updated version management via `config.VERSION` and startup printout.
- Enhanced timezone logic to default to **Pacific Time** with **NYSE/NASDAQ** calendars.

---

### 🧠 Developer Experience

- `AGENTS.md` defines architecture rules, naming conventions, and Codex task prompts.
- Codex automation pipeline now ready for fine-grained tasks (refactor, test, deploy).
- Added sanity logging and health checks for DB and Telegram integrations.

---

### 🧩 Parking Lot / Future Enhancements

- Paper-trading order flow via Alpaca (long-only MVP).
- Automatic detection of IEX vs SIP market data availability.
- Finviz + XTrades watchlist ingestion and probabilistic scoring.
- Additional metrics (Calmar, downside deviation, skew/kurtosis).
- Azure App Service webhook auto-registration post-deploy.

---

### 🧰 Migration Notes

- Run `pip install -r requirements.txt` to apply new dependencies.
- Ensure `.env` includes updated keys:  
  `TELEGRAM_WEBHOOK_SECRET`, `ALPACA_API_KEY`, `ALPACA_API_SECRET`, and `AZURE_STORAGE_CONNECTION_STRING`.
- After deploying to Azure, **immediately call**:
  <https://api.telegram.org/bot/setWebhook>
- using your **App Service URL** and `TELEGRAM_WEBHOOK_SECRET`.

---

### 🧭 Version Summary

| Component    | Status     | Notes                         |
| ------------ | ---------- | ----------------------------- |
| FastAPI Core | ✅ Stable  | Health + Telemetry wired      |
| Telegram Bot | ✅ Stable  | Verified via Postman + Mobile |
| Backtester   | ✅ Working | CLI + Unrealized PnL added    |
| Metrics      | ✅ Working | Modular & test-covered        |
| CI/CD        | ⚙️ Ready   | GitHub Actions configured     |
| Azure Deploy | 🕓 Pending | Final validation needed       |

---

**Author:** Zish Malik  
**Date:** October 26 2025  
**Version:** `0.1.1`
