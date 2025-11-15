# workers/consumer/Dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Copy only requirements first to leverage cache
COPY requirements.txt /app/requirements.txt
COPY workers/consumer/requirements.txt /app/workers/consumer/requirements.txt

RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/workers/consumer/requirements.txt && \
    python -c "import importlib.util as u; assert u.find_spec('azure.eventhub') is not None, 'azure-eventhub missing'"

# Now copy the code
COPY . /app
CMD ["python","-m","workers.consumer"]