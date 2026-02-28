FROM python:3.12-slim

WORKDIR /app

COPY migrate_topics.py topics.yaml ./

RUN pip install pyyaml kafka-python loguru

CMD ["python", "migrate_topics.py"]
