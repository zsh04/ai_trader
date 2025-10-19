# Risk Policy (Enforced)

1. **Per-Trade Risk ≤ 1%** of equity using ATR-based position sizing.
2. **Daily Drawdown Halt = 5%** — no new entries for the rest of the session/day.
3. **Manual Approval Gate** if computed order > **50%** of account value.
4. **Spread & Slippage Caps** per session; skip trades that violate.
5. **ADV Exposure Cap** — notional ≤ 0.5% of 20-day ADV.
6. **PDT Guard** — track day trades; throttle entries to avoid flag.
7. **Extended Hours** — limit+bracket only; reduced size and tighter spread cap.
8. **Kill Switch** — manual override and auto-trigger on infra/data anomalies.