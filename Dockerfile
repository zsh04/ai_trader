# Dockerfile
FROM python:3.12-slim

# System deps (psycopg2, uvicorn, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# App Service for Containers looks at WEBSITES_PORT; we’ll expose 8000.
ENV PORT=8000
EXPOSE 8000

# Gunicorn + Uvicorn worker is fine; keep it simple & prod-ish.
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-t", "90", "app.main:app", "--bind=0.0.0.0:8000"]