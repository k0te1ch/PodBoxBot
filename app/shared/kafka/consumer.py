import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from confluent_kafka import Consumer, KafkaError
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext, SerializationError
from loguru import logger

from shared.kafka.wait_for_kafka import wait_for_kafka_stack

_RETRY_INITIAL_DELAY = 2.0  # seconds
_RETRY_MAX_DELAY = 60.0  # seconds
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
        self._kafka_server = kafka_server
        self._schema_registry_url = schema_registry_url
        self._running = True
        self._closed = False
        # poll и close идут из разных потоков: замок не даёт закрыть клиент,
        # пока в нём выполняется poll.
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        self.consumer = Consumer(
            {
                "bootstrap.servers": kafka_server,
                "group.id": group_id,
                "auto.offset.reset": "earliest",
            }
        )
        self._deserializer = AvroDeserializer(SchemaRegistryClient({"url": schema_registry_url}))
        self._value_ctx = SerializationContext(topic, MessageField.VALUE)

    async def start(self, handler):
        """Async Kafka polling loop with retry backoff on transient errors.

        Перед подпиской ждём готовности Kafka и Schema Registry. Это снимает
        зависимость от порядка старта контейнеров: после ребута хоста, где
        `depends_on` не соблюдается, consumer просто дождётся зависимостей,
        вместо того чтобы стартовать в сломанном состоянии и терять события.
        """
        await wait_for_kafka_stack(self._kafka_server, self._schema_registry_url)

        self.consumer.subscribe([self.topic])
        logger.info(f"[AsyncAvroConsumer] Listening {self.topic}")

        loop = asyncio.get_event_loop()
        retry_delay = _RETRY_INITIAL_DELAY

        while self._running:
            try:
                msg = await loop.run_in_executor(self._executor, self._poll, 1.0)

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

                raw = msg.value()
                if raw is None:
                    continue
                value = await loop.run_in_executor(self._executor, self._deserializer, raw, self._value_ctx)
                if value is None:
                    continue

                _task = asyncio.create_task(handler(value))  # noqa: RUF006

            except SerializationError as e:
                # Обычно schema registry недоступна/схема не зарегистрирована.
                # Пауза, чтобы не молотить broker и логи в плотном цикле, пока
                # зависимость не восстановится.
                logger.error(f"[Kafka Avro] Serialization error: {e}")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * _RETRY_MULTIPLIER, _RETRY_MAX_DELAY)
            except Exception as e:
                logger.exception(f"[KafkaConsumer] Unexpected error: {e}")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * _RETRY_MULTIPLIER, _RETRY_MAX_DELAY)

        self.close()
        logger.info("[AsyncAvroConsumer] Stopped")

    def _poll(self, timeout: float):
        with self._lock:
            if self._closed:
                return None
            return self.consumer.poll(timeout)

    def close(self) -> None:
        """Останавливает цикл и закрывает клиент: выход из группы, коммит.

        Блокирующий вызов: ждёт текущий poll (до секунды) и ответ брокера.
        Вызывать из потока, а не из цикла событий. Повторный вызов ничего
        не делает. Без явного закрытия клиент закрывается сам при сборке
        мусора, уже на выходе из процесса и без ограничения по времени.
        """
        self._running = False
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self.consumer.close()
        self._executor.shutdown(wait=False)

    def stop(self):
        """Signal the consumer to stop gracefully."""
        logger.warning("[AsyncAvroConsumer] Stop signal received")
        self._running = False
