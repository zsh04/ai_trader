

# Changelog — Personal AI Trading Agent (Azure, Alpaca, MTF)

All notable changes to this project will be documented in this file.  
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),  
Adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]
### Planned
- Implement multi-agent system (ScannerAgent, SignalAgent, RiskAgent, MetaAgent)
- Integrate continuous learning (nightly retrain, drift detection)
- Add AI journaling & LangChain meta-evaluation
- Enhanced dashboard with Azure Monitor integration

---

## [0.1.0] — 2025-10-19
### Added
- Initial repository scaffold and complete documentation set:
  - README.md, ARCHITECTURE.md, CONFIG.md, RISK_POLICY.md, SESSION_MODEL.md, WATCHLIST_SPEC.md, DATA_SCHEMA.md, DASHBOARD_SPEC.md, CI_CD.md, RUNBOOK.md, ROADMAP.md, CONTRIBUTING.md, LICENSE, GLOSSARY.md
- Azure-first architecture:
  - App Service (Linux container)
  - Azure Blob Storage for data/models
  - Azure Database for PostgreSQL (Flexible Server) for trades, orders, journal
  - Azure Key Vault for secrets with Managed Identity
- Multi-timeframe (5m, 15m, 1h, 4h, 1D) trading architecture
- Session-aware model (PRE, REG-AM, REG-MID, REG-PM, AFT)
- Guardrails: 1% per-trade risk, 5% daily DD halt, 50% account manual gate
- Premarket and intraday scanner specifications
- Streamlit dashboard specification for live metrics
- GitHub Actions CI/CD plan for Azure deployment
- Paper trading mode support (Alpaca API integration planned)

### Notes
- This marks the **foundation release (MVP docs + infra plan)**.
- Code scaffolding and initial paper mode logic to follow in version `0.2.0`.

---

## [0.0.1] — 2025-10-15
### Created
- Project initialized by **Zish Malik** with defined scope:
  - Equities/ETFs focus
  - Cloud-native AI trading agent vision
  - Initial planning and design documentation