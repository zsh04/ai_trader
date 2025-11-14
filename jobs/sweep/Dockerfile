# syntax=docker/dockerfile:1.6
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY requirements.txt /workspace/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt \
    azure-identity azure-storage-blob loguru && rm -rf /root/.cache/pip

COPY app /workspace/app
COPY scripts/sweep_job_entry.py /workspace/scripts/sweep_job_entry.py

ENV PYTHONPATH=/workspace

ENTRYPOINT ["python", "scripts/sweep_job_entry.py"]
