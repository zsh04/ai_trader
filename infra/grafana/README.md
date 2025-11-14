# Grafana Assets

This folder stores dashboard/alert JSON that operators can import into Grafana (Cloud or AMG). Keeping the JSON in source control prevents drift and allows Terraform or manual imports to reference the same baseline.

## Files

- `router-health.json` – dashboard covering LangGraph latency, router throughput, Event Hub lag, sweep queue metrics, and recent order/fill status. Datasource placeholders:
  - `${TEMPO_DS}` – Tempo/OTLP traces datasource UID.
  - `${PROM_DS}` – Prometheus/Mimir datasource UID.
  - `${AZMON_DS}` – Azure Monitor datasource UID.
  - `${LOGANALYTICS_DS}` / `${LOG_WORKSPACE}` – Log Analytics datasource UID + workspace name.
  - `${EVENT_HUB_RESOURCE_ID}` – ARM resource ID for the Event Hubs namespace.

## Usage

1. Replace placeholder strings with the actual datasource/workspace identifiers (or binary substitute via Terraform `templatefile`).
2. Import the dashboard via Grafana UI *or* Terraform:
   ```hcl
   resource "grafana_dashboard" "router_health" {
     config_json = templatefile("${path.module}/router-health.json", {
       TEMPO_DS            = grafana_data_source.tempo.uid
       PROM_DS             = grafana_data_source.prom.uid
       AZMON_DS            = grafana_data_source.azure.uid
       LOGANALYTICS_DS     = grafana_data_source.log_analytics.uid
       LOG_WORKSPACE       = var.log_workspace_id
       EVENT_HUB_RESOURCE_ID = azurerm_eventhub_namespace.ai_trader.id
     })
     folder = grafana_folder.ops.id
     message = "AI Trader Router/EH Dashboard"
   }
   ```
3. Configure alert rules referencing the panel queries (see `docs/howto/operations/observability_dashboards.md`).
4. Commit any dashboard edits back into this folder to keep IaC and runtime view in sync.
