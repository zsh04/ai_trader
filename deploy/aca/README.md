# ACA deployment guide (ai-trader-nlp / ai-trader-forecast)

## Prerequisites

- Existing ACA environment `ai-trader-aca-env` in resource group `ai-trader-rg`.
- ACR containing the two images (see `scripts/images/build_and_push.zsh`).
- Managed Identity on each app with `Storage Blob Data Reader` on the `aitraderblobstore` account so adapters can load.
- Optional: Log Analytics workspace id for diagnostics.

Assign Storage RBAC:
```bash
az role assignment create \
  --assignee "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.ManagedIdentity/userAssignedIdentities/__OPTIONAL_MI__" \
  --role "Storage Blob Data Reader" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Storage/storageAccounts/$STG_ACCOUNT"
```
(System-assigned identities can use `--assignee-object-id $(az containerapp show ... --query identity.principalId -o tsv)`.)

## Prepare env files

Copy the provided examples and replace placeholders:
```bash
cp deploy/aca/env.nlp.example deploy/aca/.env.nlp
cp deploy/aca/env.forecast.example deploy/aca/.env.forecast
```

Populate the files with actual ACR, Log Analytics, OTEL endpoint, adapter tag, etc.

## Deploy

Container Apps can be created/updated with `az containerapp` commands:

```bash
az containerapp create \
  --resource-group $RG \
  --name ai-trader-nlp \
  --environment $ENV \
  --yaml deploy/aca/nlp.containerapp.yaml
```

For updates use `az containerapp update --yaml ...`. Repeat with `forecast.containerapp.yaml` for Chronos.

### Sweep ACA job

1. Build/push the `ai-trader-sweep` image (`make build`).
2. Populate `deploy/aca/jobs/env.sweep.example` and export the values.
3. Apply the job definition:

```bash
az containerapp job create \
  --resource-group $RG \
  --name ai-trader-sweep \
  --environment $ENV \
  --yaml deploy/aca/jobs/sweep-job.containerapp.yaml
```

Trigger executions on demand:

```bash
az containerapp job start --resource-group $RG --name ai-trader-sweep --image-version latest --env-vars SWEEP_JOB_ID=$JOB_ID SWEEP_CONFIG_BLOB=$SWEEP_CONFIG_BLOB
```

## Runtime expectations

- Both apps run internal ingress only (reachable via VNet or App-to-App).
- Health probes: `/healthz` (liveness), `/ready` (readiness).
- Scaling: min 0/max 2; CPU rule at 70% and HTTP concurrency at 5 requests.
- Env vars configure OTEL, adapter plumbing, and storage account names. The OTEL headers secret is stored inline in the manifest for readability; when applying, replace with a Key Vault reference or use `az containerapp secret set`.
