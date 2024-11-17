# Stage 1: Базовый образ для установки зависимостей
FROM python:3.12.4-slim-bullseye as base

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY pyproject.toml poetry.lock /app/

RUN apt-get update

RUN python -m pip install -U pip && \
    python -m pip install -U poetry

RUN poetry config virtualenvs.create false && \
    poetry install --only main

# FIXME: Костыль
RUN apt-get update && apt-get install -y locales
RUN sed -i -e 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen
ENV LANG ru_RU.UTF-8
ENV LC_ALL ru_RU.UTF-8

COPY . /app/


# Stage 2: Образ для запуска тестов
FROM base as test

RUN poetry install

CMD ["poetry", "run", "pytest"]


# Stage 3: Этап для выполнения миграции
FROM base as migrate

CMD ["python", "app/bot.py", "migrate"]


# Stage 4: Финальный рабочий образ
FROM base as final

CMD ["python", "app/bot.py", "run"]
