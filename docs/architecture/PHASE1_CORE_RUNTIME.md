# PHASE 1: CORE RUNTIME

The Core Runtime phase focuses on transforming raw market data into structured trading signals and executing strategies based on those signals. This involves ingesting data from various sources, normalizing it, generating technical features, applying trading strategies, managing risk, routing orders, and interacting with the broker.

```mermaid
graph TD
    %% Data ingestion sources
    AlpacaAPI[Alpaca API<br/>(Market Data Ingest)]
    Watchlist[Watchlist<br/>(Symbol Ingest)]

    %% Data normalization
    DataNormalizer[Data Normalizer<br/>(Clean & Structure Data)]

    %% Feature generation
    FeatureGen[Feature Generator<br/>(EMA, RSI, ATR)]

    %% Strategy application
    StrategyEngine[Strategy Engine<br/>(Breakout, Momentum)]

    %% Risk management
    RiskManager[Risk Manager<br/>(Position Sizing & Limits)]

    %% Order routing
    OrderRouter[Order Router<br/>(Order Execution)]

    %% Broker interface
    Broker[Broker (Alpaca)<br/>(Trade Execution)]

    %% Data flow connections
    AlpacaAPI --> DataNormalizer
    Watchlist --> DataNormalizer

    DataNormalizer --> FeatureGen

    FeatureGen --> StrategyEngine

    StrategyEngine --> RiskManager

    RiskManager --> OrderRouter

    OrderRouter --> Broker
```

### Dynamic Watchlist Ingestion
- The `/watchlist` resolver dynamically selects symbols from either the **Finviz** screener or the curated **TextList** payload.
- Runtime selection honors the positional syntax `auto|finviz|textlist [scanner] [limit] [sort]`, allowing Telegram and API clients to switch sources without redeploying.
- Fallback chain: Finviz (default for `auto`) gracefully downgrades to TextList when the screener is unavailable or returns no symbols, ensuring the feature layer maintains a valid symbol universe before feature generation begins.
