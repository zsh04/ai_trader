# How to configure bracket orders on Alpaca (paper)

> **Audience:** internal engineers/operators
>
> **Goal:** enable bracket orders (entry plus take-profit plus stop) in Alpaca paper trading so execution flows from AI Trader can stage trades safely.

## Prerequisites

- Alpaca account with **Paper** trading enabled.
- `ALPACA_API_KEY` / `ALPACA_API_SECRET` stored in Azure Key Vault (see `docs/reference/secrets.md`).
- `app/adapters/market/alpaca_client.py` available in the deployment you intend to configure.
- Python environment activated (`./scripts/dev.sh mkvenv` and `source .venv/bin/activate`).

## 1. Verify broker settings

1. Log into [paper.alpaca.markets](https://paper.alpaca.markets/) → **Paper Trading** dashboard.
2. Confirm account status shows **ACTIVE** and **Buying Power** > 0.
3. In **Settings → Trading Configuration** ensure:
   - Trade confirmations = Enabled (required for Representational State Transfer (REST) order placements).
   - Extended hours enabled if you plan to route premarket or after-hours orders (AI Trader policy uses limit orders in extended sessions).

## 2. Configure environment variables

1. Update `.env.dev` (or App Service Settings) with:

   ```bash
   ALPACA_API_KEY=your_key
   ALPACA_API_SECRET=your_secret
   ALPACA_DATA_BASE_URL=https://data.alpaca.markets/v2
   ALPACA_BASE_URL=https://paper-api.alpaca.markets
   ```

2. Sync secrets to Key Vault for production using `./scripts/kv_sync_from_env.zsh <kv-name> .env.dev`.

## 3. Enable bracket orders in code

`app/execution/alpaca_client.py` already supports bracket payloads. Ensure the `make_bracket_order` helper is configured before invoking the router.

```python
from app.execution.alpaca_client import AlpacaTradingClient

client = AlpacaTradingClient()

order = client.make_bracket_order(
    symbol="AAPL",
    qty=10,
    side="buy",
    limit_price=190.25,
    take_profit_price=194.00,
    stop_loss_price=188.50,
)
client.submit_order(order)
```

Key parameters:

- `limit_price`: entry price.
- `take_profit_price`: triggers a sell at profit.
- `stop_loss_price`: protective exit; add `stop_limit_price` if you need stop-limit behaviour.

## 4. Test with the command-line tool

1. Activate the virtual environment and export your secrets locally.
2. Use the helper script (you can add one-off tests in `scripts/adhoc/alpaca_bracket_test.py`):

   ```bash
   python scripts/adhoc/alpaca_bracket_test.py --symbol AAPL --qty 1 --entry 190.25 --tp 194 --sl 188.5
   ```

3. Confirm the order appears under **Paper → Orders** with type `bracket` and status `new`.

## 5. Integrate with AI Trader strategies

- In `app/agent/policy.py`, ensure the strategy emits structured signals containing `entry`, `take_profit`, and `stop_loss` fields.
- The in-progress `RiskManagementAgent` translates those signals into bracket orders using the helper described earlier.
- For the breakout command-line runs/backtests, feature flags (`--risk-frac-override`, upcoming `--use-brackets`) route through the same helper for parity.

## 6. Monitor and troubleshoot

- **Logs:** Search Application Insights for `component="alpaca_order"` to see the JSON payloads and Alpaca responses.
- **Common issues:**
  - `403 insufficient balance` → check buying power.
  - `400 cannot submit order` → verify bracket prices (take-profit must exceed the entry price for long orders, stop stay below).
  - `429 too many requests` → Alpaca rate limit; orders are retried with exponential backoff in the adapter.
- **Next steps:** integrate alert rules for `order_reject_total` before moving to live trading (Phase 4).

## References

- Alpaca API docs: <https://alpaca.markets/docs/trading/orders/>
- AI Trader execution adapter: `app/execution/alpaca_client.py`
