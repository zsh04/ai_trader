# How to deploy observability (OTEL → Application Insights)

## Prerequisites

- Application Insights workspace-based resource in the target subscription.
- Azure Monitor OpenTelemetry collector (Container Apps) or equivalent ingestion endpoint.
- Managed Identity with Key Vault access to store OTLP headers (`OTEL-EXPORTER-OTLP-HEADERS`).
- Updated App Service configuration with required `OTEL_*` variables.

## Procedure

1. **Provision resources**
   1. Create (or locate) the Application Insights component (`ai-trader-api`, workspace mode) and note the connection string.
   2. Deploy the Azure Monitor OTEL Container App using `infra/otel-aca.bicep` or the portal. Set `OTEL_EXPORTER_OTLP_ENDPOINT=https://ingest.monitor.azure.com/v2/track`.
   3. Configure a managed identity for the collector so it can pull OTLP headers from Key Vault.

2. **Configure application settings**
   - API/UI containers:
     ```text
     OTEL_SERVICE_NAME=ai-trader-api
     OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <ingest key>
     OTEL_RESOURCE_ATTRIBUTES=deployment.environment=prod,service.version=${APP_VERSION}
     ```
   - Store secrets in Key Vault and reference them via `@Microsoft.KeyVault(...)` App Settings.

3. **Enable code hooks**
   - `app/main.py` → call `configure_observability()` in the lifespan context.
   - `ui/streamlit_app.py` → invokes `setup_logging()` + `configure_observability()` so `/ui` traffic shares OTEL exporters (`OTEL_SERVICE_NAME=ai-trader-ui`). The playground panels now replay cached probabilistic frames without hitting vendors, so traces should show `streamlit` spans alongside API calls.
   - `app/backtest/run_breakout.py` and `app/backtest/sweeps.py` → wrap each run/job in a `backtest.run` span (attributes: `strategy`, `risk_agent`, `use_probabilistic`, `job_id`) and increment the `backtest_runs_total` counter.
   - `app/logging_utils.setup_logging()` to emit structured Loguru logs and bridge to OTEL.
   - Wrap background jobs/handlers with `logging_context(request_id=...)`.
   - For CLI/backtests, call `setup_logging()` and `configure_observability()` when OTLP env vars exist.

## Streamlit parity checklist

1. Confirm `OTEL_SERVICE_NAME=ai-trader-ui` and `OTEL_RESOURCE_ATTRIBUTES` mirror the API settings.
2. Hit `https://<fd-host>/` and verify `AppTraces` show `service.name=ai-trader-ui` spans for Streamlit requests.
3. Run a backtest via the UI or `/backtests/run`; ensure the resulting `backtest.run` span is linked to both API and Streamlit traces (trace ID available in logs).
4. For CLI-only scenarios, set `configure_observability()` env vars before invoking the runner so spans are emitted even outside App Service.

## Verification

- Logs: `curl http://<app>/health/live` then confirm `AppTraces` shows `service.version`, `environment`, `request_id`.
- Traces: generate traffic and ensure spans appear in Application Insights with IDs that match `otelTraceID` in logs.
- Metrics: check `customMetrics` (or standard runtime metrics) and inspect collector logs for export success.
- Alerts/dashboards: verify Log Analytics workbooks and Azure Monitor alerts (latency/5xx) are in place.

### Router spans & Event Hub lag

- `router.run` spans include attributes `symbol`, `strategy`, `run_id`, and link to child spans `router.node.ingest_frame`, `router.node.infer_priors`, `router.node.risk_size`, `router.node.publish_order`, `router.node.execute_order` when the corresponding toggles fire. Filter traces by `service.name=ai-trader-api` and span name prefix `router.` to validate orchestration observability.
- Grafana panels should chart `router_runs_total` (success rate) and the OTEL latency histogram (p95 budget 1.2s). Add SLO alerts mirroring Phase 3 acceptance: warn at p95 > 1.2s for 5 min, page at > 2.0s for 5 min.
- Event Hub lag: emit Azure Monitor metrics for `ai-trader-ehns/exec.orders` and alert if consumer lag > 60 s sustained over 5 min (warn) or 3 min (page). The new order consumer logs `partition_id`, `sequence_number`, and `lag_ms` (via Log Analytics query) so you can correlate router output with downstream processing.

## Troubleshooting

- **No data appears** → validate `OTEL_*` settings resolved (Key Vault refs healthy) and App Service has outbound access.
- **Missing trace IDs** → ensure `opentelemetry-instrumentation-logging` is installed and middleware/context managers are active.
- **Collector failures** → inspect Container App logs (`az containerapp logs show --name ai-trader-otel`) and restart if exporters are throttled.

## References

- Azure Monitor OTEL docs: <https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-enable>
- `docs/howto/operations/runbook.md`
