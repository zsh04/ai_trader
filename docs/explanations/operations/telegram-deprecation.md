# Telegram Deprecation Summary

The Telegram webhook/notifier stack has been retired in favour of the Streamlit console and monitoring dashboard. This note records the touchpoints that were removed and the safeguards that accompanied the cut-over.

## Surface area (removed)

- **Inbound API**: `app/api/routes/telegram.py`, wiring helpers, tests, and the `/telegram/webhook` entry point.
- **Outbound notifications**: `app/adapters/notifiers/telegram.py`, watchlist notify helpers, supporting env config, and HTTP shims.
- **Support tooling**: pytest fixtures (`tests/conftest.py`, `tests/support/telegram_sink.py`), smoke tests, and dashboard telemetry rows.

## Cut‑over highlights

1. Streamlit dashboard tabs now cover the quick actions previously issued through Telegram commands (watchlist builds, health summaries).
2. Environments temporarily used `TELEGRAM_ENABLED=0` to prove no workloads depended on the webhook before code removal.
3. The route, adapter, env settings, tests, dependencies, and documentation were deleted once the feature flag bake-in completed.
4. Bot tokens and webhook secrets were scrubbed from Key Vault and GitHub secrets.

## Streamlit replacement path

- Operators land on `/ui/` for the console and `/ui/dashboard/` for the monitoring tiles (served from the dedicated UI App Service).
- The Watchlist tab exposes the same build/refresh workflows that previously lived behind Telegram commands, including manual overrides and debug snapshots.
- Health summaries, guardrail alerts, and manual-approval prompts now surface in the dashboard cards with links back to the relevant GitHub issues/alerts.
- No additional secrets are required; the UI relies on the same Managed Identity + Key Vault mapping as the API container.

## Rollback

Reintroducing Telegram would require restoring the deleted modules/tests from version control and re-adding the dependency (`python-telegram-bot`, env settings, CI fixtures). At present there is no direct toggle to re-enable the channel.
