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
   - Traffic must flow through Azure Front Door. Access restriction `Allow-FD-Backend` (service tag `AzureFrontDoor.Backend`) should exist at priority 100 with default action `Deny`. Remove/manual override only when debugging from trusted IPs.
   - Front Door health probes use `GET /health/live` (API) and `GET /ui/` (UI); if probes show unhealthy, verify these endpoints locally before modifying FD config.
2. **Blob Storage**
   - Containers `trader-data`, `trader-models`; rotate SAS tokens if MSI isn’t used.
3. **PostgreSQL Flexible Server**
   - Tier `B1ms`, storage 32 GB, SSL required. Ensure VNet integration or outbound IP allowlisting is configured.

## Azure Event Hubs (event bus)

- **Namespace:** `ai-trader-ehns` in resource group `ai-trader-rg`.
- **Hubs:**
  - `bars.raw` (6 partitions, 24 h retention)
  - `signals.enriched` (4 partitions, 48 h retention)
  - `regimes.snapshot` (4 partitions, 48 h retention)
  - `backtest.jobs` (2 partitions, 72 h retention)
  - `exec.orders` (2 partitions, 24 h retention)
- **Consumer groups:** create `api`, `ui`, `orchestrator`, `sweeper`, and `diagnostics` on each hub.
- **Authentication:** producers/consumers use `DefaultAzureCredential` plus RBAC (`Azure Event Hubs Data Sender/Receiver`). Assign the Web App managed identities before enabling new services.
- **Checkpointing:** use Blob container `eh-checkpoints` with `EventProcessorClient` (storage account already in use for artifacts).
- **Environment/Key Vault keys:**
  ```text
  EH_FQDN=ai-trader-ehns.servicebus.windows.net
  EH_HUB_BARS=bars.raw
  EH_HUB_SIGNALS=signals.enriched
  EH_HUB_REGIMES=regimes.snapshot
  EH_HUB_JOBS=backtest.jobs
  EH_HUB_ORDERS=exec.orders
  EH_CONSUMER_GROUP=orchestrator
  CHECKPOINT_CONTAINER=eh-checkpoints
  ```
- **Verification:**
  ```bash
  az eventhubs eventhub list -g ai-trader-rg --namespace-name ai-trader-ehns \
    --query '[].{name:name,partitions:partitionCount,retentionH:retentionDescription.retentionTimeInHours}' -o table
  ```
- **Status:** API + Streamlit managed identities now have `Azure Event Hubs Data Sender/Receiver` and `Storage Blob Data Contributor` (container `eh-checkpoints` exists). Future services must be granted the same roles when they adopt the bus.
- **Open items:** wire Private Link/VNet integration once origins move behind private endpoints.

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

## Front Door / routing verification

1. Fetch the active endpoint host:
   ```bash
   FD_HOST=$(az afd endpoint show -g ai-trader-rg --profile-name fd-ai-trader -n fd-ai-trader-endpoint --query hostName -o tsv)
   ```
2. Smoke routes:
   ```bash
   curl -sS -o /dev/null -w '/ -> % {http_code}\n'        "https://$FD_HOST/"
   curl -sS -o /dev/null -w '/ui -> % {http_code}\n'      "https://$FD_HOST/ui"
   curl -sS -o /dev/null -w '/health/live -> % {http_code}\n' "https://$FD_HOST/health/live"
   curl -sS -o /dev/null -w '/docs -> % {http_code}\n'    "https://$FD_HOST/docs"
   ```
3. Confirm the Front Door routes are linked to the default domain:
   ```bash
   az afd route list -g ai-trader-rg --profile-name fd-ai-trader --endpoint-name fd-ai-trader-endpoint \
     --query '[].{name:name,link:properties.linkToDefaultDomain,patterns:properties.specificPathsToMatch}' -o table
   ```
4. If the UI 404s at `/`, ensure `route-ui` has `originPath=/ui/` (with trailing slash) and that `route-ui-prefix` (patterns `/ui`, `/ui/*`) has `originPath=null`.
5. Keep Web App access restrictions in sync with FD:
   - `Allow-FD-Backend` (service tag `AzureFrontDoor.Backend`) @ priority 100.
   - Optional office allow rule @ 110 when needed.
   - Default deny for all others (SCM inherits rules unless explicitly overridden).

## DAL smoke test (Alpha Vantage + Finnhub)

Use `scripts/dal_smoke.py` after migrations or credential updates to confirm the DAL pulls from every vendor we depend on. The script hits Alpaca, Alpha Vantage (intraday + daily), Yahoo, Twelve Data, and Finnhub by default and writes a JSON manifest for audit.

1. **Set vendor API keys** (shell export or `.env.dev`):
   ```bash
   export ALPHAVANTAGE_API_KEY=... \
          FINNHUB_API_KEY=...
   ```
2. **Run the harness** (installs nothing; uses the repo virtualenv):
   ```bash
   source .venv/bin/activate
   python scripts/dal_smoke.py \
     --output-dir artifacts/ops/dal_smoke
   ```
   - Optional: add `--check vendor:symbol:interval:lookbackDays` to probe custom routes.
3. **Review the report** at `artifacts/ops/dal_smoke/dal_smoke_<timestamp>.json`. Each entry lists bar/signal/regime counts and cache paths. Failures (`status="error"`) bubble up via exit code 1 so CI can gate deployments.
4. **Pass criteria:** Alpha Vantage returns several hundred intraday bars (with matching signal/regime counts) and Finnhub returns the most recent daily quote. Investigate API keys or plan limits if any vendor returns zero rows or errors.
5. **Record results** in the sprint status doc so everyone knows the last verified timestamp (or review the `DAL Smoke` GitHub Action run, which stores the latest JSON report artifact).

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

### Streamlit probabilistic frame viewer

The Streamlit console now reads the persisted probabilistic frames (from both CLI and sweep runs) directly from the new manifest at `artifacts/probabilistic/frames/manifest.jsonl`.

1. Trigger a backtest run (CLI or API) and confirm `prob_frame_path` is logged in the response.
2. Open the Streamlit dashboard (`/ui` via Front Door) and expand **Backtest Sweeps → Probabilistic Frame Viewer**.
3. Select the sweep/job entry (or paste a manual path) to render the merged probabilistic DataFrame, metadata (row counts, columns, time range), and recent rows.
4. Use this view to debug DAL issues without re-fetching vendors; the underlying parquet file is shared between CLI, API, and Streamlit.

## LangGraph router smoke

Use the router endpoint to verify ingest → priors → risk sizing → AEH publish flow (offline mode avoids vendor usage and exercises the kill-switch path).

```bash
curl -sS -X POST https://$FD_HOST/router/run \
  -H "Content-Type: application/json" \
  -d '{
        "symbol": "AAPL",
        "start": "2025-01-02T00:00:00Z",
        "strategy": "breakout",
        "offline_mode": true,
        "publish_orders": true,
        "execute_orders": false
      }'
```

Pass criteria:

- Response contains `events` including `ingest:synthetic`, `priors:computed`, `risk:fractional_kelly`, and `order:published`.
- Event Hub `exec.orders` receives the intent (visible via `scripts/check_quicksend_eventhubs.py` / Log Analytics).
- Setting `kill_switch_active=true` (or lowering `kill_switch_notional` via payload) returns `fallback_reason` `kill_switch_*` and no order is published, confirming the kill-switch guard is healthy.

Notes:

- `publish_orders=true` requires `EH_HUB_ORDERS`/`EH_FQDN` env + RBAC; use `publish_orders=false` when Event Hubs is unavailable.
- `execute_orders=true` requires Alpaca keys (`ALPACA_API_KEY/SECRET`) and should only be used in paper/live environments after verifying kill-switch metrics.

## Order consumer service

Use `scripts/order_consumer.py` (or the ACA job equivalent) to persist router intents from `exec.orders` into the `trading.orders`/`trading.fills` tables so the API/UI can surface them without bespoke database access.

```bash
python scripts/order_consumer.py \
  EH_FQDN=ai-trader-ehns.servicebus.windows.net \
  EH_HUB_ORDERS=exec.orders \
  EH_CONSUMER_GROUP=orchestrator \
  STORAGE_ACCOUNT=aitraderblobstore \
  CHECKPOINT_CONTAINER=eh-checkpoints
```

- The consumer upserts each order into Postgres, creates fill rows when payloads contain `fills[]`, and checkpoints to Blob Storage (unless the storage env vars are omitted). When running locally, set `LOCAL_DEV=1` to authenticate via `az login`.
- Confirm rows via `/orders?limit=20` or the Streamlit “Router Orders” tab.
- If lag grows beyond 60 s, recycle the consumer job or inspect Event Hub metrics.

### Surfacing orders/fills via API + UI

Production Streamlit deployments no longer open direct database connections. Instead, set:

```text
API_BASE_URL=https://<fd-host>
API_BEARER_TOKEN=<ops token or managed identity header>
```

The dashboard now falls back to `GET /orders` and `GET /fills` when `DATABASE_URL` is absent, so ACA-hosted or restricted environments still visualize router outputs in near-real time.

## Sweep orchestrator job

Container Apps job `ai-trader-sweep` (see `deploy/aca/jobs/sweep-job.containerapp.yaml`) executes `scripts/sweep_job_entry.py`. Provide the sweep config path via `SWEEP_CONFIG_PATH` or set `SWEEP_CONFIG_BLOB=blob://configs/<file>` so the job downloads the YAML from `aitraderblobstore`. Optional `SWEEP_OUTPUT_DIR` writes results to a mounted share.

```bash
SWEEP_CONFIG_PATH=configs/backtest/momentum_sweep.yaml \
OUTPUT_DIR=artifacts/backtests/momentum \
python scripts/sweep_job_entry.py
```

Use `POST /backtests/sweeps/jobs` to enqueue an ACA execution (payload contains `config_path`, `strategy`, `symbol`); the endpoint publishes to `EH_HUB_JOBS` and records state in the manifest so `/backtests/sweeps/jobs` and Streamlit can display queue/running/completed counts.

The script still invokes `app.backtest.sweeps.run_sweep`, writes artifacts/summary JSONL files (consumed by Streamlit), and logs run metadata. The dashboard now reads job status from the API instead of the local manifest, so ACA + Web App stay in sync.

### Sweep job consumer

Run `scripts/sweep_job_consumer.py` (or deploy it as a Container Apps job) to process `EH_HUB_JOBS` messages and start the ACA sweep job automatically. Required env vars:

```
EH_FQDN=ai-trader-ehns.servicebus.windows.net
EH_HUB_JOBS=backtest.jobs
EH_CONSUMER_GROUP_SWEEP=sweeper
SWEEP_JOB_RESOURCE_ID=/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.App/jobs/ai-trader-sweep
SWEEP_JOB_CONTAINER=sweep-job
STORAGE_ACCOUNT=aitraderblobstore
CHECKPOINT_CONTAINER=eh-checkpoints
```

The consumer authenticates with Managed Identity (or Azure CLI when `LOCAL_DEV=1`) and calls the Container Apps `start` API with job-specific env overrides (`SWEEP_CONFIG_BLOB`, `SWEEP_JOB_ID`, etc.). Successful dispatches log a `dispatched` status in `sweep_registry`, so Streamlit and the API can show live state.

## References

- `docs/howto/operations/observability.md`
- `docs/howto/operations/azure-backup.md`
- `internal/research-docs/code_summary.md`
