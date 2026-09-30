# syntax=docker/dockerfile:1
# Stage 1: Базовый образ для установки зависимостей
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates curl git openssh-client locales && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем локаль ru_RU.UTF-8
RUN sed -i 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen && \
    echo "LANG=ru_RU.UTF-8" > /etc/default/locale
ENV LANG=ru_RU.UTF-8
ENV LC_ALL=ru_RU.UTF-8

RUN python -m pip install --upgrade pip && \
    python -m pip install poetry==2.3.4

COPY app/publishers/WordPress/pyproject.toml app/publishers/WordPress/poetry.lock /app/
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

COPY app/shared /app/shared/
COPY app/publishers/WordPress /app/

FROM base AS final
CMD ["python", "main.py"]
