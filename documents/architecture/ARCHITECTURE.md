# AI Trader Architecture Overview

AI Trader is designed with a modular architecture that separates concerns into distinct phases, ensuring scalability, reliability, and maintainability. Each phase focuses on a specific aspect of the trading system, from core runtime operations and observability to backtesting, execution, and documentation generation. This layered approach facilitates clear development workflows and robust system integration.

## Core Runtime Phase

The Core Runtime phase encompasses the essential components responsible for data ingestion, feature engineering, model inference, and agent decision-making. This phase forms the backbone of AI Trader's operational logic.

```mermaid
graph TD
  A[Data Sources\n(Alpaca/Polygon)] --> B[Data Loader]
  B --> C[Feature Layer\n(MTF aggregator, indicators)]
  C --> D[Models\n(signal, regime, risk)]
  D --> E[Agent\n(policy, sizing, risk gates)]
  E --> F[Execution\n(Alpaca API, bracket orders)]
  E --> G[Journal & Eval\n(meta-agent, summaries)]
  F --> H[Monitoring\n(Streamlit, metrics)]
  A -->|Premarket scans| I[ScannerAgent]
  I --> J[UniverseAgent]
  J --> C
```

## Reliability & Observability Phase

This phase ensures that AI Trader operates reliably with comprehensive monitoring, logging, and alerting systems. It supports proactive detection and resolution of issues.

```mermaid
graph TD
  M[Metrics Collector\n(Prometheus)] --> N[Alert Manager]
  O[Log Aggregator\n(ELK Stack)] --> P[Dashboard\n(Kibana)]
  H[Monitoring\n(Streamlit, metrics)] --> M
  H --> O
  N --> Q[Incident Response]
```

## Backtesting Phase

The Backtesting phase allows rigorous evaluation of trading strategies using historical data, enabling performance analysis and strategy refinement before live deployment.

```mermaid
graph TD
  R[Historical Data Loader] --> S[Feature Layer\n(Same as Core)]
  S --> T[Backtest Engine]
  T --> U[Performance Metrics\n(Sharpe, Drawdown)]
  U --> V[Strategy Optimization]
  V --> W[Backtest Reports]
```

## Execution Phase

Execution handles the live deployment of trading decisions, order management, and integration with broker APIs, ensuring timely and accurate trade execution.

```mermaid
graph TD
  E[Agent\n(policy, sizing, risk gates)] --> X[Order Manager]
  X --> Y[Broker API\n(Alpaca)]
  Y --> Z[Order Status & Fills]
  Z --> G[Journal & Eval\n(meta-agent, summaries)]
  Z --> H[Monitoring\n(Streamlit, metrics)]
```

## Documentation & Codex Phase

This phase supports automated documentation generation and AI-assisted code exploration, enhancing developer productivity and system transparency.

```mermaid
graph TD
  AA[Codebase] --> AB[Doc Generator\n(MkDocs, Sphinx)]
  AA --> AC[AI Codex\n(Code Search, Q&A)]
  AB --> AD[Documentation Site]
  AC --> AE[Developer Tools]
```
