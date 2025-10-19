# CI/CD (Azure)

**CI (GitHub Actions)**
- Lint: ruff
- Test: pytest
- Security: bandit
- Build: Docker image → GHCR (or Azure Container Registry optional)

**CD (Azure App Service, Linux container)**
- Deploy container to **App Service** with `azure/webapps-deploy@v2`.
- Scheduled jobs via **GitHub Actions cron** calling a protected webhook on the app for: premarket scans, refreshes, EOD retrain.

**Secrets**
- Store in GitHub Encrypted Secrets; at runtime fetch from **Azure Key Vault** (recommended) using a **User-Assigned Managed Identity** on App Service.

**Networking (recommended)**
- App Service ↔ PostgreSQL Flexible Server via **VNet integration** and **private DNS**.
- App Service to Blob via public endpoint with restricted **Storage firewall + private endpoints** (optional). 