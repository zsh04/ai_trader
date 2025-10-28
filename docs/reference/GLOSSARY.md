

# Glossary — Personal AI Trading Agent

### General Trading Terms
- **ADV (Average Daily Volume):** Average number of shares traded per day over a period (usually 20 days).
- **ATR (Average True Range):** Volatility indicator measuring the average range of price movement.
- **RVOL (Relative Volume):** Ratio comparing current trading volume to average volume, used to gauge unusual activity.
- **PDT (Pattern Day Trader Rule):** FINRA rule requiring $25,000 minimum balance if more than 3 intraday trades are made in 5 business days.
- **MAE (Maximum Adverse Excursion):** Largest unrealized loss during a trade.
- **MFE (Maximum Favorable Excursion):** Largest unrealized gain during a trade.
- **R Multiple:** Reward-to-risk ratio of a trade, calculated as profit divided by risk amount.
- **DD (Drawdown):** Reduction from peak equity to trough; used to measure risk and performance degradation.
- **VWAP (Volume Weighted Average Price):** Weighted average of prices by volume; benchmark for institutional trades.
- **SSR (Short Sale Restriction):** Regulation preventing short sales when a stock falls more than 10% in a day.
- **Bracket Order:** Order with attached Stop-Loss (SL) and Take-Profit (TP) levels for automatic risk management.

### AI / ML Terms
- **Drift Detection:** Identifying changes in data distribution that degrade model accuracy.
- **PSI (Population Stability Index):** Metric for detecting data drift between two distributions.
- **HMM (Hidden Markov Model):** Probabilistic model for inferring hidden states such as market regimes.
- **SHAP (SHapley Additive exPlanations):** Framework for interpreting model feature importance.
- **XGBoost:** Gradient-boosting ML algorithm used for fast, interpretable classification.
- **LangChain:** Framework for building reasoning and memory-based AI agents.
- **LLM (Large Language Model):** AI model trained on large text corpora to perform reasoning, journaling, and summaries.
- **Meta-Agent:** Supervisory AI layer that monitors performance and suggests parameter adjustments.
- **Drift Rollback:** Process of reverting to a previously stable model after drift detection.

### Market Microstructure
- **Order Book:** Real-time list of buy and sell orders for a security.
- **Spread:** Difference between best bid and best ask prices; proxy for liquidity.
- **Liquidity:** Ease of entering/exiting positions without significant price impact.
- **Slippage:** Difference between expected and executed trade price due to volatility or liquidity.
- **Imbalance:** Volume difference between buy and sell orders, often predictive of short-term direction.

### Sessions
- **PRE:** Premarket (04:00–09:30 PT)
- **REG-AM:** Regular Market Morning (09:30–11:30 PT)
- **REG-MID:** Regular Market Midday (11:30–14:00 PT)
- **REG-PM:** Regular Market Afternoon (14:00–16:00 PT)
- **AFT:** After-hours (16:00–20:00 PT)

### Data & Infrastructure
- **Azure Blob Storage:** Cloud object storage for data and models.
- **Azure Database for PostgreSQL:** Managed database for trade, order, and journal persistence.
- **Azure App Service:** Cloud hosting environment for running the trading agent container.
- **Key Vault:** Azure service for managing secrets (API keys, DB passwords).
- **Managed Identity:** Azure authentication method allowing secure access to other services without credentials.

### Strategy & Risk
- **Kelly Criterion:** Formula for optimal bet sizing based on win probability and payoff ratio.
- **Risk per Trade:** Percentage of account equity risked on a single trade (1% default).
- **Daily Drawdown Halt:** Automated stop when account drops by 5% from starting day equity.
- **Manual Approval Gate:** Human verification step when order size exceeds 50% of account value.
- **Session Metrics:** Performance breakdown per trading session (PnL, hit rate, Sharpe).

### Backtesting & Performance
- **Expectancy:** Average profit per trade over time; (Win% × AvgWin) − (Loss% × AvgLoss).
- **Sharpe Ratio:** Risk-adjusted return metric comparing excess returns to volatility.
- **Equity Curve:** Cumulative account value progression across trades.
- **Out-of-Sample:** Evaluation on unseen data to verify generalization.
- **Paper Trading:** Simulated trading using real data without financial risk.