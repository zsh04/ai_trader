# Observability Deployment Guide

This note captures how we instrument AI Trader with OpenTelemetry and ship data to
Azure Application Insights via the managed Collector.

## 1. Application Insights & Collector Provisioning

1. **Create Application Insights resource**
   - Resource group: `ai-trader-prod`
   - Workspace-based mode
   - Note the connection string (`APPLICATIONINSIGHTS_CONNECTION_STRING`)

2. **Deploy Azure Monitor OpenTelemetry Distro (Container Apps)**
   - Use the provided Bicep/ARM template in `infra/otel-aca.bicep` (or the portal)
   - `OTEL_EXPORTER_OTLP_ENDPOINT` → `https://ingest.monitor.azure.com/v2/track`
   - Configure managed identity with Key Vault access to OTEL secrets if needed

3. **Configure env vars for API/UI containers**
   - `OTEL_SERVICE_NAME=ai-trader-api` (or ui)
   - `OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <ingest key>`
   - Optional: `OTEL_RESOURCE_ATTRIBUTES=deployment.environment=prod,service.version=${APP_VERSION}`

4. **Key Vault references**
   - Store ingest headers / secrets in Key Vault (`OTEL-EXPORTER-OTLP-HEADERS`)
   - Apps pull via App Settings references (@Microsoft.KeyVault(...))

## 2. Code Hooks

- `app/main.py` calls `configure_observability()` during lifespan.
- `app/logging_utils.setup_logging()` ensures structured Loguru output and bridges to stdlib/OTEL.
- Use `logging_context(request_id=...)` (from `app.logging_utils`) around request handlers / background jobs.
- For CLI/backtest scripts, invoke `setup_logging()` and optionally `configure_observability()` if OTLP
  env vars are present.

## 3. Health Verification Checklist

1. **Logs**
   - Trigger a request (`curl http://localhost:8000/health/live`)
   - Confirm Log Analytics table `AppTraces` shows `service.version`, `environment`, `request_id`.

2. **Traces**
   - Generate traffic through API.
   - View end-to-end spans in Application Insights → Transactions.
   - Ensure trace IDs in logs (`otelTraceID`) match span IDs in AI.

3. **Metrics**
   - Verify custom metrics under `customMetrics` (if configured) or standard runtime metrics.
   - Check collector logs for export success.

4. **Alerts / Dashboards**
   - Configure Log Analytics queries / Workbooks as needed using the resource.
   - Health checks: `az monitor app-insights component show --app ai-trader-api`

5. **CI Validation**
   - `ci-api.yml` and `ci-ui.yml` run lint, `bandit`, `pip-audit`, and `pytest` every PR to catch regressions.

## 4. Troubleshooting

- **No data appearing**
  - Confirm `OTEL_*` variables in App Settings resolved (Key Vault references are green).
  - Check App Service diagnostic logs for exporter errors.
  - Ensure outbound network access to Azure Monitor ingestion endpoints.

- **Missing trace IDs in logs**
  - Verify `opentelemetry-instrumentation-logging` is installed and `configure_logging()` is enabled.
  - Ensure `logging_context` or `logger.contextualize` wraps each request in middleware.

- **Collector failures**
  - Inspect Container App logs (`az containerapp logs show --name ai-trader-otel`)
  - Restart the collector app if exporters are throttled.

Keep this guide updated as we change observability tooling or destinations.
