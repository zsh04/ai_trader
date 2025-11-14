-include .env

.PHONY: build push seed deploy-nlp deploy-forecast deploy-sweep-job smoke

build:
	./scripts/images/build_and_push.zsh

push:
	ACR_NAME=$${ACR_NAME:?set ACR_NAME} ./scripts/images/build_and_push.zsh

seed:
	STG_ACCOUNT=$${STG_ACCOUNT:?set STG_ACCOUNT} HF_REPO=$${HF_REPO:-ProsusAI/finbert} ./scripts/models/populate_blob_from_hf.zsh finbert
	STG_ACCOUNT=$${STG_ACCOUNT:?set STG_ACCOUNT} HF_REPO=$${HF_REPO_CHRONOS:-amazon/chronos-2} ./scripts/models/populate_blob_from_hf.zsh chronos2

deploy-nlp:
	az containerapp create --resource-group $${RG:?set RG} --name ai-trader-nlp --environment $${ENV:?set ENV} --yaml deploy/aca/nlp.containerapp.yaml

deploy-forecast:
	az containerapp create --resource-group $${RG:?set RG} --name ai-trader-forecast --environment $${ENV:?set ENV} --yaml deploy/aca/forecast.containerapp.yaml

deploy-sweep-job:
	az containerapp job create --resource-group $${RG:?set RG} --name ai-trader-sweep --environment $${ENV:?set ENV} --yaml deploy/aca/jobs/sweep-job.containerapp.yaml

smoke:
	./scripts/smoke/curl_nlp.sh
	./scripts/smoke/curl_forecast.sh
