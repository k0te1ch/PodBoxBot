# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# libgomp: OpenMP, на котором ctranslate2 считает модель на CPU.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates libgomp1 && \
    rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip && \
    python -m pip install poetry==2.3.4

COPY app/transcriber/pyproject.toml app/transcriber/poetry.lock /app/
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-root

COPY app/shared/transcribe /app/shared/transcribe/
COPY app/transcriber /app/

CMD ["python", "main.py"]
