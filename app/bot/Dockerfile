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

# Устанавливаем локаль ru_RU.UTF-8
RUN sed -i 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen && \
    echo "LANG=ru_RU.UTF-8" > /etc/default/locale
ENV LANG=ru_RU.UTF-8
ENV LC_ALL=ru_RU.UTF-8

# Устанавливаем Poetry и необходимые инструменты сборки
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install poetry==2.3.4

# Копируем файлы зависимостей и устанавливаем их
COPY app/bot/pyproject.toml app/bot/poetry.lock /app/
# Настраиваем Poetry для работы без виртуальных окружений

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

# Копируем исходный код
COPY app/shared /app/shared/
COPY app/bot /app/
COPY files /app/files/
COPY static /app/static/
# CHANGELOG.md (номер версии) и release-notes (русский текст для админов)
# нужны on_startup для релиз-ноута (send_release_note). Без них бот не
# падает, но админам уйдёт только номер версии или ничего.
COPY CHANGELOG.md /app/CHANGELOG.md
COPY release-notes /app/release-notes/

ENV SCHEMA_REGISTRY_URL=http://schema-registry:8081

CMD ["bash", "-c", "python /app/shared/register_schemas.py && python main.py"]


# Stage 2: Образ для запуска тестов
FROM base AS test
RUN poetry install --with dev
CMD ["poetry", "run", "pytest"]

# Stage 3: Этап для выполнения миграции
FROM base AS migrate
CMD ["python", "main.py", "migrate"]

# Stage 4: Финальный рабочий образ
FROM base AS final
CMD ["python", "main.py", "run"]
