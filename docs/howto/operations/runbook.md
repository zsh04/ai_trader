# Operations runbook

## Prerequisites

- Access to Azure subscription resources (App Service, Blob Storage, PostgreSQL Flexible Server).
- PM2 installed on any long-running VM used for log rotation.
- Managed identity and Key Vault references configured (see `docs/howto/operations/managed-identity.md`).

## Daily schedule (Pacific Time)

| Time | Action |
|------|--------|
| 03:58 | Start container / confirm App Service is running |
| 04:00 | Premarket scan (rough watchlist) |
| 06:15 | Finalize opening watchlist |
| 09:25 | Warm-up; 09:30 regular session open |
| 09:35 / 11:30 / 13:30 | Intraday refresh cycles |
| 16:05 | After-hours scan |
| 17:30 | Retrain (when enabled) |
| 18:00 | Reports / summaries |

## Azure operations checklist

1. **App Service (API & UI)**
   - Linux container, Managed Identity enabled, `WEBSITES_PORT` aligned with uvicorn port.
2. **Blob Storage**
   - Containers `trader-data`, `trader-models`; rotate SAS tokens if MSI isn’t used.
3. **PostgreSQL Flexible Server**
   - Tier `B1ms`, storage 32 GB, SSL required. Ensure VNet integration or outbound IP allowlisting is configured.

## Post-deployment steps

1. Tail App Service logs until the new container reports healthy:
   ```bash
   az webapp log tail -n "$WEBAPP_NAME" -g "$RESOURCE_GROUP"
   ```
2. Flush local PM2 logs if applicable:
   ```bash
   pm2 flush ai-trader
   ```
3. Hit `/health/live` and `/health/ready` and confirm HTTP 200.

## DAL smoke test (Alpha Vantage + Finnhub)

Run this validation after migrations or vendor credential updates to ensure the probabilistic data layer feeds the Streamlit UI.

1. **Set vendor API keys** (temporary shell export or use `.env.dev`):
   ```bash
   export ALPHAVANTAGE_API_KEY=... \
          FINNHUB_API_KEY=...
   ```
2. **Execute the smoke script** (uses the live DAL):
   ```bash
   PYTHONPATH=. python - <<'PY'
   from datetime import datetime, timedelta, timezone
   from app.dal.manager import MarketDataDAL

   now = datetime.now(timezone.utc)
   dal = MarketDataDAL(enable_postgres_metadata=False)

   av = dal.fetch_bars("AAPL", start=now - timedelta(days=5), end=now,
                      interval="5Min", vendor="alphavantage")
   print("Alpha Vantage bars", len(av.bars.data))

   fh = dal.fetch_bars("AAPL", start=now - timedelta(days=30), end=now,
                      interval="1Day", vendor="finnhub")
   print("Finnhub bars", len(fh.bars.data))
   PY
   ```
3. **Pass criteria:** Alpha Vantage returns thousands of intraday bars with matching signal/regime counts, and Finnhub returns the latest daily quote. Investigate vendor credentials or rate limits if either response is empty/errored.
4. **Record results** in the sprint log / Confluence so ops knows the last verified timestamp.

## Probabilistic backtest validation

Use this CLI run after code changes to momentum/mean-reversion/risk management so we confirm the end-to-end wiring (DAL → strategy → Fractional Kelly) still functions. It also drops the merged probabilistic frame under `artifacts/probabilistic/frames` for Streamlit reuse.

1. Activate the virtualenv and export a temporary output directory so we do not litter the repo:
   ```bash
   source .venv/bin/activate
   export BACKTEST_NO_SAVE=1 BACKTEST_OUT_DIR=$(mktemp -d)
   ```
2. Run a DAL-backed CLI invocation (the vendor can be Yahoo to avoid API limits):
   ```bash
   python -m app.backtest.run_breakout \
     --symbol AAPL --start 2023-01-03 --end 2023-02-03 \
     --strategy momentum --use-probabilistic \
     --dal-vendor yahoo --dal-interval 1Day \
     --risk-agent fractional_kelly --risk-agent-fraction 0.4 \
     --regime-aware-sizing --debug
   ```
3. **Pass criteria:**
   - Logs show the DAL fetch succeeded with matching counts for bars/signals/regimes.
   - Fractional Kelly logs a capped risk fraction (`prob=... frac=...`).
   - A frame file appears under `artifacts/probabilistic/frames/AAPL_momentum_yahoo_1day.parquet`.
4. Capture the command output in the sprint status doc so we have an auditable timestamp for the last smoke test.

## References

- `docs/howto/operations/observability.md`
- `docs/howto/operations/azure-backup.md`
