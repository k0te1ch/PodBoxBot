"""Сквозной прогон событий через живые Kafka и Schema Registry.

Проверяет то, что юнит-тесты не видят: сериализатор регистрирует схему,
брокер отдаёт байты, а consumer разбирает их обратно в тот же dict. Отдельно
проверена совместимость со старым `confluent_kafka.avro.AvroProducer` — в
топиках прода лежат сообщения, записанные именно им.
"""

import asyncio
import json
import uuid
import warnings
from pathlib import Path

import pytest

from shared.kafka.consumer import KafkaConsumer
from shared.kafka.producer import KafkaProducer

SCHEMAS_DIR = Path(__file__).parents[3] / "app" / "shared" / "kafka" / "schemas"
SCHEMA_FILES = sorted(SCHEMAS_DIR.glob("*.avsc"))


def _sample(avro_type):
    if isinstance(avro_type, list):
        non_null = [t for t in avro_type if t != "null"]
        return _sample(non_null[0]) if non_null else None
    if isinstance(avro_type, dict):
        if avro_type["type"] == "array":
            return [_sample(avro_type["items"])]
        if avro_type["type"] == "map":
            return {"ключ": _sample(avro_type["values"])}
        if avro_type["type"] == "record":
            return {f["name"]: _sample(f["type"]) for f in avro_type["fields"]}
        return _sample(avro_type["type"])
    return {
        "string": "значение",
        "int": 7,
        "long": 7,
        "boolean": True,
        "float": 1.5,
        "double": 1.5,
    }[avro_type]


def _record(schema_path: Path) -> dict:
    return _sample(json.loads(schema_path.read_text(encoding="utf-8")))


async def _consume_one(bootstrap: str, registry: str, topic: str) -> dict:
    consumer = KafkaConsumer(bootstrap, registry, topic, group_id=f"e2e-{uuid.uuid4()}")
    received: asyncio.Queue = asyncio.Queue()

    async def handler(value):
        await received.put(value)

    loop_task = asyncio.create_task(consumer.start(handler))
    try:
        return await asyncio.wait_for(received.get(), timeout=60)
    finally:
        consumer.stop()
        await asyncio.wait_for(loop_task, timeout=15)


@pytest.mark.asyncio
@pytest.mark.parametrize("schema_path", SCHEMA_FILES, ids=lambda p: p.stem)
async def test_producer_to_consumer(kafka_stack, schema_path):
    bootstrap, registry = kafka_stack
    topic = f"e2e-{schema_path.stem}-{uuid.uuid4().hex[:8]}"
    record = _record(schema_path)

    await KafkaProducer(bootstrap, registry, str(schema_path)).send(topic, record)

    assert await _consume_one(bootstrap, registry, topic) == record


@pytest.mark.asyncio
async def test_consumer_reads_legacy_avro_producer(kafka_stack):
    bootstrap, registry = kafka_stack
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from confluent_kafka import avro
        from confluent_kafka.avro import AvroProducer

    schema_path = SCHEMAS_DIR / "boosty_event.avsc"
    topic = f"e2e-legacy-{uuid.uuid4().hex[:8]}"
    record = _record(schema_path)
    legacy = AvroProducer(
        {"bootstrap.servers": bootstrap, "schema.registry.url": registry},
        default_value_schema=avro.loads(schema_path.read_text(encoding="utf-8")),
    )
    legacy.produce(topic=topic, value=record)
    legacy.flush()

    assert await _consume_one(bootstrap, registry, topic) == record
