

# Contributing Guide — Personal AI Trading Agent (Azure, Alpaca, MTF)

Thank you for your interest in contributing! This project aims to build an AI-driven, fully autonomous trading agent deployed on Azure using Alpaca APIs, Azure Blob Storage, and Azure PostgreSQL.

---

## 🧱 Repository Structure Overview
```
app/
  ├── agent/           # Policy, risk, sizing, meta-agent
  ├── scanners/        # Premarket & intraday scanners
  ├── sessions/        # Session clock and tagging
  ├── models/          # ML models, trainer, registry
  ├── execution/       # Alpaca client, order router
  ├── monitoring/      # Dashboard, metrics
  ├── data/            # Data loader, store
  └── utils/           # Helpers, logging, config
```

---

## 🧩 Development Setup

### 1. Environment Setup
- Python 3.11+  
- `pip install -r requirements.txt`
- Copy `.env.example` → `.env` and fill in:
  - Alpaca API credentials  
  - Azure Blob connection string  
  - Azure PostgreSQL connection string  
  - Runtime flags and thresholds  

### 2. Database Setup
Run the schema migration:
```bash
psql "$PGDATABASE" -f scripts/schema.sql
```

### 3. Lint, Test, Build
```bash
ruff check .
pytest -v
```

### 4. Local Run (Paper Mode)
```bash
python -m app.main --mode paper
```

---

## 🌐 Cloud Deployment (Azure)

### GitHub Actions
CI/CD automatically:
- Lints, tests, and builds Docker image
- Pushes to GHCR (or Azure Container Registry)
- Deploys to Azure App Service (Linux container)
- Runs scheduled jobs via webhook triggers

### Secrets Management
- Use **Azure Key Vault** with **Managed Identity**
- No secrets should be stored in `.env` on production

---

## 🧠 Coding Standards

### Python
- Follow [PEP8](https://peps.python.org/pep-0008/) and use **ruff** for linting
- Type hints required for all function definitions
- Use **f-strings** for string formatting
- Favor **dataclasses** for structured entities
- Use **logging** (no print statements)

### Git
- Feature branches: `feature/<description>`
- Bug fixes: `fix/<issue>`
- Each PR must include:
  - Description of changes
  - Testing evidence (unit or integration)
  - Updated docs if config or interface changed

---

## 🧪 Testing
- Unit tests for:
  - Risk management logic
  - Sizing and guardrails
  - Data integrity (session tagging)
- Integration tests:
  - Alpaca paper trading
  - Azure Blob and Postgres connectivity
- Use mocks for APIs and database during CI

---

## 📊 Documentation
All code additions must include or update documentation:
- Module-level docstrings for new files
- Inline comments for non-obvious logic
- Update relevant Markdown specs (e.g., `CONFIG.md`, `RUNBOOK.md`)

---

## 🛡 Risk & Safety Review
Every change affecting execution or risk logic must undergo manual review:
- Validate `MAX_RISK_PER_TRADE`, `DAILY_DRAWDOWN_HALT`, `CONCENTRATION_MANUAL_GATE`
- Ensure proper enforcement in `app/agent/risk.py`

---

## 🧩 Pull Request Workflow
1. Fork or branch from `main`
2. Make your changes locally
3. Run full test suite
4. Submit PR with clear description
5. Await review by maintainers (Zish or delegated reviewer)
6. Upon merge, CI/CD deploys automatically to Azure App Service (staging)

---

## 🧰 Optional Developer Tools
- **VSCode Extensions:**
  - Python
  - Docker
  - Azure Tools
  - Ruff
- **CLI Utilities:**
  - `az` for Azure CLI
  - `mlflow` for model tracking
  - `pgcli` for Postgres interaction

---

## ✅ Definition of Done
A contribution is considered complete when:
- [ ] All CI checks pass (lint, tests, security)
- [ ] Docs updated (README, CONFIG, or relevant spec)
- [ ] No unhandled exceptions or print debugging
- [ ] Backwards compatibility maintained
- [ ] Deployment verified on Azure (staging)

---

## 🙌 Acknowledgements
Contributors will be recognized in `docs/CONTRIBUTORS.md` after their first merged PR.  
Let's build a reliable, transparent, and open AI trading system together.
