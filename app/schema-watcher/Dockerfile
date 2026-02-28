FROM python:3.12-slim

WORKDIR /app

COPY app/shared/kafka/schemas /app/shared/schemas
COPY app/schema-watcher/register_schemas_watcher.py /app/register_schemas_watcher.py

RUN pip install --no-cache-dir requests

ENV SCHEMA_REGISTRY_URL=http://schema-registry:8081

CMD ["python", "/app/register_schemas_watcher.py"]
