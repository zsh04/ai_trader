# Runbook

## Daily Schedule (PT)
- 03:58 Start container
- 04:00 Premarket scan (watchlist rough)
- 06:15 Finalize Opening Watchlist
- 09:25 Warm-up; 09:30 Open
- 09:35/11:30/13:30 Refresh cycles
- 16:05 After-hours scan; 17:30 Retrain; 18:00 Reports

## Azure Operations
- **App Service**: Linux container; enable **Managed Identity**; set `WEBSITES_PORT` if using FastAPI/uvicorn non-default.
- **Blob Storage**: create containers `trader-data`, `trader-models`; rotate SAS if not using MSI.
- **PostgreSQL Flexible Server**: tier **B1ms** (burstable), storage 32GB; **SSL required**; configure VNet or allow App Service outbound IPs; set

## Post-Deployment Steps
- **Run Telegram webhook setup:**

  ```bash
  curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
    -H "Content-Type: application/json" \
    -d '{"url":"'$APP_URL'/telegram/webhook","secret_token":"'$TELEGRAM_WEBHOOK_SECRET'"}'
  ```

- **Tail Azure logs:**

  ```bash
  az webapp log tail -n "$WEBAPP_NAME" -g "$RESOURCE_GROUP"
  ```

- **Rotate logs (local):**

  ```bash
  pm2 flush ai-trader
  ```
