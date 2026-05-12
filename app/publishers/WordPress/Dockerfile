# Stage 1: Базовый образ для установки зависимостей
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates curl locales && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем локаль ru_RU.UTF-8
RUN sed -i 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen && \
    echo "LANG=ru_RU.UTF-8" > /etc/default/locale
ENV LANG=ru_RU.UTF-8
ENV LC_ALL=ru_RU.UTF-8

RUN python -m pip install --upgrade pip && \
    python -m pip install --upgrade poetry

COPY app/publishers/WordPress/pyproject.toml /app/
RUN poetry config virtualenvs.create false && \
    poetry lock && \
    poetry install --only main --no-root

COPY app/shared /app/shared/
COPY app/publishers/WordPress /app/

FROM base AS final
CMD ["python", "main.py"]
