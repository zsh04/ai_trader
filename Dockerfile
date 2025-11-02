# Dockerfile
FROM python:3.13-slim

# System deps (psycopg2, uvicorn, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- ADD THESE TWO LINES ---
# Install the OpenTelemetry packages
RUN pip install --no-cache-dir "opentelemetry-distro[otlp]"

# Run the auto-instrumentation (this installs opentelemetry-instrument)
RUN opentelemetry-bootstrap -a install
# --- END OF ADDED LINES ---

# Copy app
COPY . .

# App Service for Containers looks at WEBSITES_PORT; we’ll expose 8000.
ENV PORT=8000
EXPOSE 8000

# The CMD remains the same.
# The env vars will be provided by Docker Compose or Azure.
CMD ["opentelemetry-instrument", "uvicorn", "app.main:app", "--host", "0.0.0.0"]