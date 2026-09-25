import asyncio
from pathlib import Path

from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext
from loguru import logger

from shared.kafka.wait_for_kafka import wait_for_kafka_stack


class KafkaProducer:
    def __init__(self, kafka_server: str, schema_registry_url: str, value_schema_path: str):
        self.kafka_server = kafka_server
        self.schema_registry_url = schema_registry_url
        self.value_schema_path = value_schema_path

        # Конструктор только сохраняет конфиг. Avro-схему грузим и producer
        # (сериализатор тянется к schema registry / брокеру) создаём лениво при
        # первом send — это позволяет инстанцировать publisher'ы без доступа к
        # Kafka и без .avsc по in-container пути (нужно для тестов вне контейнера).
        self.producer: Producer | None = None
        self._serializer: AvroSerializer | None = None
        self._ready = False

    def _ensure_producer(self) -> tuple[Producer, AvroSerializer]:
        """Лениво грузит Avro-схему и поднимает producer с сериализатором (idempotent)."""
        if self.producer is None or self._serializer is None:
            schema_str = Path(self.value_schema_path).read_text(encoding="utf-8")
            registry = SchemaRegistryClient({"url": self.schema_registry_url})
            self._serializer = AvroSerializer(registry, schema_str)
            self.producer = Producer({"bootstrap.servers": self.kafka_server})
        return self.producer, self._serializer

    async def send(self, topic: str, value: dict):
        # Перед первой публикацией дожидаемся Kafka + Schema Registry. Иначе
        # после ребута хоста (где порядок старта не гарантирован) первый send
        # упал бы на недоступной schema registry, и событие потерялось бы.
        # Флаг кэширует готовность — на горячем пути проверки нет.
        if not self._ready:
            await wait_for_kafka_stack(self.kafka_server, self.schema_registry_url)
            self._ready = True

        producer, serializer = self._ensure_producer()
        ctx = SerializationContext(topic, MessageField.VALUE)
        loop = asyncio.get_event_loop()
        payload = await loop.run_in_executor(None, serializer, value, ctx)
        await loop.run_in_executor(None, lambda: producer.produce(topic=topic, value=payload))
        producer.flush()
        logger.info(f"[KafkaProducer] Sent to {topic}: {value}")
