# Watchlist Specification

**Generation:**
- 04:00 PRE scan → rough list
- 06:15 PRE finalize → Opening Watchlist
- 09:35, 11:30, 13:30, 16:05 refreshes

**Filters:** price $1–$10, gap% ≥ 5, RVOL ≥ 3, premarket $ volume ≥ $1M, spread ≤ 0.75%, optional float ≤ 100M, optional news flag.

**Ranking:** dollar volume ↓, gap%, momentum strength, spread quality.

**Outputs:** `data/watchlists/YYYY-MM-DD.json` with fields: symbol, price, gap_pct, rvol, spread_pct, dollar_vol, float_est, session_eligibility.