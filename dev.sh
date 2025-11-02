#!/bin/zsh

# dev.sh
# Loads development environment variables and runs the app with OTel instrumentation.

echo "🚀 Starting AI Trader in DEV mode..."

# Load the .env.dev file
# This command finds all lines in .env.dev, removes comments (#),
# and exports them as environment variables for this script's session.
export $(grep -v '^#' .env.dev | grep -E '.+=.+' | xargs)

# Run the app
# opentelemetry-instrument wraps the uvicorn command,
# reads the OTEL_ environment variables, and configures telemetry.
opentelemetry-instrument uvicorn app.main:app --host 0.0.0.0 --reload