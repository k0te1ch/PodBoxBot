# syntax=docker/dockerfile:1
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
    ca-certificates curl git openssh-client locales && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
RUN python -m pip install --upgrade pip && \
    python -m pip install poetry==2.3.4

# Копируем файлы зависимостей и устанавливаем их
COPY app/publishers/FTP/pyproject.toml app/publishers/FTP/poetry.lock /app/
# sagenza-tgbot-sdk лежит в приватном репозитории: read-only deploy-ключ
# приходит BuildKit-секретом sdk_deploy_key (compose берёт его из
# secrets/sdk_deploy_key) и в слои образа не попадает.
RUN --mount=type=secret,id=sdk_deploy_key,required=false \
    poetry config virtualenvs.create false && \
    poetry config system-git-client true && \
    if [ -s /run/secrets/sdk_deploy_key ]; then \
      export GIT_SSH_COMMAND="ssh -i /run/secrets/sdk_deploy_key -o StrictHostKeyChecking=accept-new" && \
      git config --global url."git@github.com:k0te1ch/sagenza-tgbot-sdk".insteadOf "https://github.com/k0te1ch/sagenza-tgbot-sdk"; \
    fi; \
    poetry install --only main --no-root; \
    status=$?; rm -f /root/.gitconfig; exit $status

# Копируем исходный код FTP-паблишера
COPY app/shared /app/shared/
COPY app/publishers/FTP /app/

# Stage 4: Финальный рабочий образ
FROM base AS final
CMD ["python", "main.py"]
