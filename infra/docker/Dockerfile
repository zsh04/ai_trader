# Dockerfile
FROM python:3.13-slim

ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
LABEL org.opencontainers.image.version="$APP_VERSION"

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

# Surface build version inside the image for runtime introspection
RUN echo "$APP_VERSION" > /app/_build_version.txt

# App Service for Containers looks at WEBSITES_PORT; we’ll expose 8000.
ENV PORT=8000
EXPOSE 8000

# The CMD remains the same.
# The env vars will be provided by Docker Compose or Azure.
CMD ["opentelemetry-instrument", \
    "gunicorn", \
    "-k", "uvicorn.workers.UvicornWorker", \
    "-w", "2", \
    "-t", "90", \
    "app.main:app", \
    "--bind", "0.0.0.0:8000"]
