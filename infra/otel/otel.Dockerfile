# Use the same collector image from your docker-compose.yml
FROM otel/opentelemetry-collector-contrib:latest

# Copy your existing config file (with ${VAR_NAME} placeholders)
# into the image. Azure will inject the env vars at runtime.
COPY collector-config.yml /etc/otelcol-contrib/config.yaml
