---
title: Model artifact tracker
doc_type: reference
audience: internal
product_area: data
last_verified: 2025-11-11
toc: true
---

# Model artifact tracker

Single source of truth for the hybrid adapter builds used by AI Trader.

| Service | HF model | HF commit SHA | Baked adapter tag | Effective adapter (runtime) | Build base | Image tag(s) | Notes |
|---------|----------|---------------|-------------------|------------------------------|-----------|--------------|-------|
| ai-trader-nlp | ProsusAI/finbert | `<set via HF_COMMIT_SHA>` | `<baked>` | `<runtime>` | python:3.12-slim | `ai-trader-nlp:<tag>` | Update after each build. |
| ai-trader-forecast | amazon/chronos-2 | `<set via HF_COMMIT_SHA>` | `<baked>` | `<runtime>` | python:3.12-slim | `ai-trader-forecast:<tag>` | Replace notes when Chronos inference lands. |

> If a service must fall back to python:3.11-slim (e.g., missing wheels), record the reason in the *Build base* column.

## Adapter location cheat sheet

```
models/<service>/<hf_sha>/...
adapters/<service>/<adapter_tag>/adapter.tar.gz
```

Both containers log the resolved adapter metadata to `/models-cache/<service>/effective.json` and expose it via OTEL resource attributes (`ai.adapter.tag`).
