# Stage 1: Базовый образ для установки зависимостей
FROM python:3.12-slim AS base

# Отключаем кеширование байт-кода Python и включаем вывод без буфера
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Рабочая директория
WORKDIR /app

# Обновляем системные пакеты и устанавливаем необходимые утилиты.
# git нужен Poetry для установки зависимостей из git-репозиториев
# (system-git-client ниже) — встроенный dulwich-клиент на этом ломается.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates curl git locales && \
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
    python -m pip install --upgrade poetry

# Копируем файлы зависимостей и устанавливаем их
COPY app/bot/pyproject.toml app/bot/poetry.lock /app/
# Настраиваем Poetry для работы без виртуальных окружений

RUN poetry config virtualenvs.create false && \
    poetry config system-git-client true && \
    poetry install --only main --no-root

# Копируем исходный код
COPY app/shared /app/shared/
COPY app/bot /app/
COPY files /app/files/
COPY static /app/static/
# CHANGELOG.md нужен on_startup для release-note (send_release_note).
# Без него код падает на FileNotFoundError — теперь графично обрабатывается,
# но иметь файл всё равно правильно.
COPY CHANGELOG.md /app/CHANGELOG.md

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
