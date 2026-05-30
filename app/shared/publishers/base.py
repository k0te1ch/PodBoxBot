"""BasePublisher — общий Kafka-loop для publisher'ов.

Подклассы заявляют пять class-атрибутов (name, event_cls, schema_path,
upload_topic, result_topic, group_id) и реализуют `publish(event)`. База
сама:

* поднимает KafkaConsumer + KafkaProducer на конфиге shared.config;
* валидирует входящий payload через event_cls;
* меряет длительность и шлёт success/failure-счётчики в Pushgateway;
* при исключении в `publish` собирает failure-result event (по умолчанию
  через model_copy + override полей status/error/event_type) и отправляет
  в result_topic, чтобы бот апдейтил TG-сообщение пользователя.

Aftershow-эпизоды (`event.type_episode == "aftershow"`) — это маркер
для платных publisher'ов: VK Donut, Boosty, Patreon, sponsr должны
ставить им paywall. Хелпер `is_paywalled(event)` инкапсулирует это
правило, чтобы при изменении логики (например, появится «patron-only»
тип) правка была в одном месте.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from loguru import logger
from pydantic import BaseModel

from shared.config import config
from shared.kafka.consumer import KafkaConsumer
from shared.kafka.producer import KafkaProducer
from shared.publishers.metrics import PublisherMetrics


class BasePublisher(ABC):
    """Общая обёртка Kafka-loop'а для всех publisher'ов."""

    # --- Subclass contract ---
    name: str
    """Short identifier used for log lines, metric names и job-имени."""

    event_cls: type[BaseModel]
    """Pydantic-модель события, на которое подписан publisher."""

    schema_path: str
    """Путь к .avsc внутри контейнера (для AvroProducer)."""

    upload_topic: str
    """Топик, который publisher слушает."""

    result_topic: str
    """Топик, в который publisher шлёт result-события (бот их потребляет)."""

    group_id: str
    """Consumer group для horizontal-scalability (на одного potребителя)."""

    def __init__(
        self,
        kafka_server: str | None = None,
        schema_registry_url: str | None = None,
    ) -> None:
        kafka_server = kafka_server or config.KAFKA_SERVER
        schema_registry_url = schema_registry_url or config.SCHEMA_REGISTRY_URL

        self._consumer = KafkaConsumer(
            kafka_server=kafka_server,
            schema_registry_url=schema_registry_url,
            topic=self.upload_topic,
            group_id=self.group_id,
        )
        self.producer = KafkaProducer(
            kafka_server=kafka_server,
            schema_registry_url=schema_registry_url,
            value_schema_path=self.schema_path,
        )
        self.metrics = PublisherMetrics(self.name)

    # --- Subclass hooks ---

    @abstractmethod
    async def publish(self, event) -> None:
        """Выполняет платформо-специфичную публикацию.

        При успехе подкласс сам отправляет в self.result_topic success-event
        с подробностями. При неудаче — поднимает исключение, база сама
        соберёт и отправит failure-event.
        """

    @staticmethod
    def is_paywalled(event) -> bool:
        """True если эпизод предназначен для платной аудитории.

        Платные publisher'ы (VK Donut, Boosty, Patreon, sponsr) должны
        выставлять соответствующий tier/donut_paid флаг. Бесплатные
        (FTP, WordPress) могут это поле игнорировать.
        """
        return getattr(event, "type_episode", None) == "aftershow"

    def event_key(self, event) -> str:
        """Человекочитаемый ключ события для логов / метрических лейблов.

        Дефолт пытается file_name → number → '?'. Подкласс может
        переопределить, если в его схеме другой главный идентификатор.
        """
        return getattr(event, "file_name", None) or getattr(event, "number", None) or "?"

    def build_failure_event(self, event, error: str):
        """Собирает failure-result event для отправки в result_topic.

        Дефолт — model_copy исходного с переопределением event_type/status/
        error. Подкласс может вернуть свою сборку, если в схеме есть
        поля, требующие обнуления (например, прогресс).
        """
        return event.model_copy(
            update={
                "event_type": "result",
                "status": "failure",
                "error": error,
            }
        )

    # --- Main loop ---

    async def _handle(self, payload: dict) -> None:
        """Один цикл: валидация → publish → метрики → failure-fallback.

        Этот метод — единая точка тестирования. Тесты могут вызывать его
        напрямую, минуя Kafka consumer.
        """
        try:
            event = self.event_cls(**payload)
        except Exception as e:
            logger.error(f"Invalid {self.event_cls.__name__} payload: {e}")
            return

        key = self.event_key(event)
        logger.info(f"Received {self.name} upload request from {event.username} for {key}")

        start = time.time()
        try:
            await self.publish(event)
            self.metrics.success({"target": str(key)})
        except Exception as e:
            logger.exception(f"Failed to publish {self.name}/{key}: {e}")
            self.metrics.failure({"target": str(key)})
            try:
                failure = self.build_failure_event(event, str(e))
                await self.producer.send(self.result_topic, failure.model_dump())
            except Exception as e2:
                logger.error(f"Failed to emit failure result for {self.name}/{key}: {e2!r}")
        finally:
            self.metrics.duration(
                {"target": str(key), "user": event.username},
                time.time() - start,
            )
            await self.metrics.push()

    async def run(self) -> None:
        """Запустить consumer-цикл. Блокирует."""
        await self._consumer.start(self._handle)
