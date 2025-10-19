# Architecture

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