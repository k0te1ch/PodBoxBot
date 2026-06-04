import asyncio

from confluent_kafka import avro
from confluent_kafka.avro import AvroProducer
from loguru import logger

from shared.kafka.wait_for_kafka import wait_for_kafka_stack


class KafkaProducer:
    def __init__(self, kafka_server: str, schema_registry_url: str, value_schema_path: str):
        self.kafka_server = kafka_server
        self.schema_registry_url = schema_registry_url
        self.value_schema_path = value_schema_path

        # Конструктор только сохраняет конфиг. Avro-схему грузим и AvroProducer
        # (он сразу тянется к schema registry / брокеру) создаём лениво при
        # первом send — это позволяет инстанцировать publisher'ы без доступа к
        # Kafka и без .avsc по in-container пути (нужно для тестов вне контейнера).
        self.value_schema = None
        self.producer: AvroProducer | None = None
        self._ready = False

    def _ensure_producer(self) -> AvroProducer:
        """Лениво грузит Avro-схему и поднимает AvroProducer (idempotent)."""
        if self.producer is None:
            self.value_schema = avro.load(self.value_schema_path)
            self.producer = AvroProducer(
                {
                    "bootstrap.servers": self.kafka_server,
                    "schema.registry.url": self.schema_registry_url,
                },
                default_value_schema=self.value_schema,
            )
        return self.producer

    async def send(self, topic: str, value: dict):
        # Перед первой публикацией дожидаемся Kafka + Schema Registry. Иначе
        # после ребута хоста (где порядок старта не гарантирован) первый send
        # упал бы на недоступной schema registry, и событие потерялось бы.
        # Флаг кэширует готовность — на горячем пути проверки нет.
        if not self._ready:
            await wait_for_kafka_stack(self.kafka_server, self.schema_registry_url)
            self._ready = True

        producer = self._ensure_producer()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: producer.produce(topic=topic, value=value))
        producer.flush()
        logger.info(f"[AvroProducer] Sent to {topic}: {value}")
