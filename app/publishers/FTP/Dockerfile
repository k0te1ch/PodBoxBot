# Stage 1: Базовый образ для установки зависимостей
FROM python:3.12-slim AS base

# Отключаем кеширование байт-кода Python и включаем вывод без буфера
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Рабочая директория
WORKDIR /app

# Обновляем системные пакеты и устанавливаем необходимые утилиты
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates curl locales && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
RUN python -m pip install --upgrade pip && \
    python -m pip install --upgrade poetry

# Копируем файлы зависимостей и устанавливаем их
COPY app/publishers/FTP/pyproject.toml app/publishers/FTP/poetry.lock /app/
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-root

# Копируем исходный код FTP-паблишера
COPY app/shared /app/shared/
COPY app/publishers/FTP /app/

# Stage 4: Финальный рабочий образ
FROM base AS final
CMD ["python", "main.py"]
