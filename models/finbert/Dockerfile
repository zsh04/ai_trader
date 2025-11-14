# syntax=docker/dockerfile:1.6
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates libgomp1 build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY models/common /workspace/models/common
COPY models/finbert/app /workspace/app
COPY models/finbert/entrypoint.sh /workspace/entrypoint.sh

# Install Python deps (CPU-only torch)
RUN pip install --upgrade pip \
    && pip install "torch==2.6.*" --index-url https://download.pytorch.org/whl/cpu \
    && pip install \
    "transformers>=4.43,<5" \
    "accelerate>=0.33,<1" \
    "peft>=0.13,<1" \
    "fastapi>=0.110,<1" \
    "uvicorn[standard]>=0.29,<1" \
    "pydantic>=2,<3" \
    "orjson>=3.9,<4" \
    loguru \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp \
    opentelemetry-instrumentation-fastapi \
    azure-identity \
    azure-storage-blob \
    && rm -rf /root/.cache/pip

ENV MODEL_CACHE_DIR=/models-cache \
    HF_HOME=/models-cache/.cache/huggingface \
    TRANSFORMERS_CACHE=/models-cache/.cache/huggingface/hub

RUN mkdir -p /models-cache && chmod 777 /models-cache && chmod +x /workspace/entrypoint.sh

# Create unprivileged user
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /workspace /models-cache
USER appuser

ARG APP_VERSION=dev
ARG HF_COMMIT_SHA=unknown
ARG ADAPTER_TAG=base
ARG BUILD_DATE

LABEL org.opencontainers.image.version="${APP_VERSION}" \
    org.opencontainers.image.revision="${HF_COMMIT_SHA}" \
    ai.model.source="hf://ProsusAI/finbert" \
    ai.hf.repo.sha="${HF_COMMIT_SHA}" \
    ai.adapter.version="${ADAPTER_TAG}" \
    ai.build.date="${BUILD_DATE:-unknown}"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["/workspace/entrypoint.sh"]
