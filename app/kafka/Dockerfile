FROM python:3.12-slim

WORKDIR /app

COPY migrate_topics.py topics.yaml ./

RUN pip install --no-cache-dir pyyaml kafka-python loguru

CMD ["python", "migrate_topics.py"]
