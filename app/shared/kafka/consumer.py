import asyncio
from concurrent.futures import ThreadPoolExecutor

from confluent_kafka.avro import AvroConsumer, SerializerError
from loguru import logger


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
        """Асинхронное прослушивание Kafka"""
        self.consumer.subscribe([self.topic])
        logger.info(f"[AsyncAvroConsumer] Listening {self.topic}")

        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # poll запускается в отдельном треде, не блокирует event loop
                msg = await loop.run_in_executor(
                    self._executor, self.consumer.poll, 1.0
                )

                if msg is None:
                    continue
                if msg.error():
                    logger.error(f"[Kafka Error] {msg.error()}")
                    continue

                value = msg.value()
                if value is None:
                    continue

                # каждая обработка сообщения — отдельная асинхронная задача
                asyncio.create_task(handler(value))

            except SerializerError as e:
                logger.error(f"[Kafka Avro] Ошибка сериализации: {e}")
            except Exception as e:
                logger.exception(f"[KafkaConsumer] Ошибка: {e}")

        self.consumer.close()
        logger.info("[AsyncAvroConsumer] Остановлен")

    def stop(self):
        """Остановка consumer"""
        logger.warning("[AsyncAvroConsumer] Получен сигнал на остановку")
        self._running = False
