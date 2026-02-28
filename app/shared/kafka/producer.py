import asyncio

from confluent_kafka import avro
from confluent_kafka.avro import AvroProducer
from loguru import logger


class KafkaProducer:
    def __init__(
        self, kafka_server: str, schema_registry_url: str, value_schema_path: str
    ):
        self.kafka_server = kafka_server
        self.schema_registry_url = schema_registry_url

        # Загружаем Avro схему
        self.value_schema = avro.load(value_schema_path)

        self.producer = AvroProducer(
            {
                "bootstrap.servers": kafka_server,
                "schema.registry.url": schema_registry_url,
            },
            default_value_schema=self.value_schema,
        )

    async def send(self, topic: str, value: dict):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: self.producer.produce(topic=topic, value=value)
        )
        self.producer.flush()
        logger.info(f"[AvroProducer] Sent to {topic}: {value}")
