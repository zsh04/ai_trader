# How to run CI/CD for AI Trader

## Prerequisites

- GitHub Actions runners with access to the repository and GitHub secrets (`AZURE_WEBAPP_NAME`, `AZURE_RESOURCE_GROUP`, etc.).
- Azure App Service (Linux container) for the API (and Streamlit UI when ready).
- Azure Container Registry or GitHub Container Registry credentials for pushing images.
- Managed Identity + Key Vault wiring per `docs/howto/operations/managed-identity.md` and `docs/reference/secrets.md`.

## Procedure

1. **Configure CI pipeline (GitHub Actions)**
   - Lint: `ruff check .`
   - Security: `bandit --severity-level medium --confidence-level low -r app scripts tests`
   - Tests: `pytest -q`
   - Build: Docker image tagged with SHA → GHCR or ACR.

2. **Configure CD pipeline**
   - Use `azure/webapps-deploy@v2` to deploy the built image to the App Service (API and, later, UI).
   - For scheduled tasks (premarket scans, refreshes, retrain), create GitHub Actions workflows with `schedule` triggers that call protected `/tasks/*` webhooks using a token.

3. **Manage secrets & networking**
   - Store GitHub secrets for build-time values only; runtime secrets should come from Key Vault via Managed Identity (`@Microsoft.KeyVault(...)` references in App Settings).
   - Integrate App Service with the VNet that hosts PostgreSQL Flexible Server; add private DNS entries or firewall rules as needed.
   - Restrict Storage account access (firewall or private endpoints) if the app needs Blob access.

## Verification

- [ ] Latest CI run shows lint/test/security jobs green.
- [ ] Container image for the target commit exists in GHCR/ACR.
- [ ] App Service shows the updated image tag and `/health/ready` returns 200 after deployment.
- [ ] Scheduled workflows successfully call the protected webhooks (check Action logs and API logs).

## References

- GitHub Actions docs: <https://docs.github.com/actions>
- Azure Web Apps deploy action: <https://github.com/Azure/webapps-deploy>
- `docs/howto/operations/observability.md` for post-deploy monitoring steps
