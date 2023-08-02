# Build image
FROM python:3.10.10-slim-bullseye as base

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt


# Тестовый образ
FROM base as test
CMD [ "python", "-m pytest", "--rootdir ." ]


# Итоговый образ, в котором будет работать бот
FROM base as production
COPY --from=base /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY . /app
CMD [ "python", "bot.py", "run"]