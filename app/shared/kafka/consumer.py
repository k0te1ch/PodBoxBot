import asyncio
from concurrent.futures import ThreadPoolExecutor

from confluent_kafka import KafkaError
from confluent_kafka.avro import AvroConsumer, SerializerError
from loguru import logger

_RETRY_INITIAL_DELAY = 2.0   # seconds
_RETRY_MAX_DELAY = 60.0      # seconds
_RETRY_MULTIPLIER = 2.0


class KafkaConsumer:
    def __init__(
        self,
        kafka_server: str,
        schema_registry_url: str,
        topic: str,
        group_id: str,
        max_workers: int = 4,
    ):
        self.topic = topic
        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        self.consumer = AvroConsumer(
            {
                "bootstrap.servers": kafka_server,
                "group.id": group_id,
                "auto.offset.reset": "earliest",
                "schema.registry.url": schema_registry_url,
            }
        )

    async def start(self, handler):
        """Async Kafka polling loop with retry backoff on transient errors."""
        self.consumer.subscribe([self.topic])
        logger.info(f"[AsyncAvroConsumer] Listening {self.topic}")

        loop = asyncio.get_event_loop()
        retry_delay = _RETRY_INITIAL_DELAY

        while self._running:
            try:
                msg = await loop.run_in_executor(self._executor, self.consumer.poll, 1.0)

                if msg is None:
                    continue

                if msg.error():
                    error = msg.error()
                    if error.code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                        logger.warning(
                            f"[AsyncAvroConsumer] Topic not available yet: {self.topic}. "
                            f"Retrying in {retry_delay:.0f}s"
                        )
                        await asyncio.sleep(retry_delay)
                        retry_delay = min(retry_delay * _RETRY_MULTIPLIER, _RETRY_MAX_DELAY)
                        continue

                    logger.error(f"[Kafka Error] {error}")
                    continue

                # Reset backoff after a successful message
                retry_delay = _RETRY_INITIAL_DELAY

                value = msg.value()
                if value is None:
                    continue

                _task = asyncio.create_task(handler(value))  # noqa: RUF006

            except SerializerError as e:
                logger.error(f"[Kafka Avro] Serialization error: {e}")
            except Exception as e:
                logger.exception(f"[KafkaConsumer] Unexpected error: {e}")

        self.consumer.close()
        logger.info("[AsyncAvroConsumer] Stopped")

    def stop(self):
        """Signal the consumer to stop gracefully."""
        logger.warning("[AsyncAvroConsumer] Stop signal received")
        self._running = False
