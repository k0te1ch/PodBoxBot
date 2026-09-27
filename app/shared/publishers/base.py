"""BasePublisher — общий Kafka-loop для publisher'ов.

Подклассы заявляют пять class-атрибутов (name, event_cls, schema_path,
upload_topic, result_topic, group_id) и реализуют `publish(event)`. База
сама:

* поднимает KafkaConsumer + KafkaProducer на конфиге shared.config;
* валидирует входящий payload через event_cls;
* меряет длительность и шлёт success/failure-счётчики в Pushgateway;
* повторяет внешние вызовы через `call_with_retry` (retry из
  sagenza_tgbot_sdk) и на каждую неудачную попытку шлёт result-event со
  статусом `retrying` и metadata (stage/attempt/attempts), чтобы бот
  сообщил админу;
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

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TypeVar

from loguru import logger
from pydantic import BaseModel
from sagenza_tgbot_sdk.resilience import PermanentError, retry, verify_published

from shared.config import config
from shared.kafka.consumer import KafkaConsumer
from shared.kafka.producer import KafkaProducer
from shared.publishers.metrics import PublisherMetrics

T = TypeVar("T")


class StepFailedError(Exception):
    """Шаг публикации не удался после всех попыток."""

    def __init__(self, stage: str, attempts: int, error: BaseException) -> None:
        super().__init__(f"{stage}: {error} (попыток: {attempts})")
        self.stage = stage
        self.attempts = attempts


class BasePublisher(ABC):
    """Общая обёртка Kafka-loop'а для всех publisher'ов."""

    # --- Subclass contract ---
    name: str
    """Short identifier used for log lines, metric names и job-имени."""

    event_cls: type[BaseModel]
    """Pydantic-модель события, на которое подписан publisher."""

    schema_path: str
    """Путь к .avsc внутри контейнера (для KafkaProducer)."""

    upload_topic: str
    """Топик, который publisher слушает."""

    result_topic: str
    """Топик, в который publisher шлёт result-события (бот их потребляет)."""

    group_id: str
    """Consumer group для horizontal-scalability (на одного potребителя)."""

    # --- Capability flags ---
    # Декларативные дефолты. Оркестратор/роутер может смотреть на них, чтобы
    # не слать событие туда, где возможность не реализована (например, не
    # отправлять paid_only-эпизод в publisher с supports_paywall=False).
    supports_paywall: bool = False
    """True если publisher умеет ставить paywall/tier (Boosty, sponsr, VK Donut)."""

    supports_scheduled: bool = False
    """True если publisher умеет отложенную публикацию по расписанию."""

    # --- Retry policy ---
    retry_attempts: int = 3
    """Сколько раз всего пробовать внешний вызов (подкласс берёт из конфига)."""

    retry_backoff: float = 5.0
    """Пауза перед второй попыткой, дальше растёт экспоненциально."""

    verify_attempts: int = config.VERIFY_ATTEMPTS
    verify_backoff: float = config.VERIFY_BACKOFF

    retry_sleep: Callable[[float], Awaitable[None]] = staticmethod(asyncio.sleep)
    """Пауза между попытками; тесты подменяют на no-op."""

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

    async def _ensure_auth(self) -> None:
        """Гарантирует валидные креды перед publish. No-op по умолчанию.

        Token-based publisher'ы (Boosty: access/refresh/device из auth.json)
        переопределяют: загрузить токен из файла, при истечении/401 — refresh
        и пересохранить. Blocking file IO заворачивать в asyncio.to_thread.
        Бесплатные publisher'ы (FTP, WordPress) ничего не делают.

        Вызывается базой в начале каждого _handle; исключение здесь
        конвертируется в failure-event так же, как из publish().
        """
        return None

    @staticmethod
    def is_paywalled(event) -> bool:
        """True если эпизод предназначен для платной аудитории.

        Два источника правды, в порядке приоритета:
        1. Явный `paywall_tier` — если задан, эпизод платный (любой непустой
           tier означает «только для подписчиков этого уровня и выше»).
        2. `type_episode == "aftershow"` — исторический неявный маркер.

        Платные publisher'ы (VK Donut, Boosty, Patreon, sponsr) выставляют
        tier; бесплатные (FTP, WordPress) поле игнорируют.
        """
        if getattr(event, "paywall_tier", None):
            return True
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

    def build_retry_event(self, event, error: str, metadata: dict[str, str]):
        """Result-event о неудачной попытке, после которой будет повтор."""
        failure = self.build_failure_event(event, error)
        return failure.model_copy(update={"status": "retrying", "metadata": metadata})

    async def _report_retry(self, event, stage: str, attempt: int, attempts: int, error: BaseException) -> None:
        key = str(self.event_key(event))
        self.metrics.retry({"target": key, "stage": stage})
        metadata = {"stage": stage, "attempt": str(attempt), "attempts": str(attempts)}
        try:
            retry_event = self.build_retry_event(event, f"{type(error).__name__}: {error}", metadata)
            await self.producer.send(self.result_topic, retry_event.model_dump())
        except Exception as e:
            logger.error(f"Failed to emit retry result for {self.name}/{key}: {e!r}")

    async def call_with_retry(
        self,
        event,
        stage: str,
        func: Callable[[], Awaitable[T]],
        *,
        attempts: int | None = None,
        backoff: float | None = None,
    ) -> T:
        """Выполняет ``func`` с повторами; каждая неудачная попытка, кроме
        последней, уходит в result_topic событием ``retrying``.

        После последней неудачи поднимает :class:`StepFailedError` — база
        превратит его в failure-event с тем же stage в metadata.
        """
        total = attempts or self.retry_attempts
        attempt = 0

        async def _once() -> T:
            nonlocal attempt
            attempt += 1
            try:
                return await func()
            except PermanentError:
                raise
            except Exception as e:
                if attempt < total:
                    await self._report_retry(event, stage, attempt, total, e)
                raise

        runner = retry(
            attempts=total,
            backoff=self.retry_backoff if backoff is None else backoff,
            sleep=self.retry_sleep,
        )(_once)
        try:
            return await runner()
        except Exception as e:
            raise StepFailedError(stage, attempt, e) from e

    async def verify(self, event, url: str, **kwargs) -> None:
        """Проверяет, что пост доступен по ``url`` (с повторами).

        kwargs пробрасываются в ``verify_published`` (session, contains).
        """
        await self.call_with_retry(
            event,
            "verify",
            lambda: verify_published(url, **kwargs),
            attempts=self.verify_attempts,
            backoff=self.verify_backoff,
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
            await self._ensure_auth()
            await self.publish(event)
            self.metrics.success({"target": str(key)})
        except Exception as e:
            logger.exception(f"Failed to publish {self.name}/{key}: {e}")
            self.metrics.failure({"target": str(key)})
            try:
                failure = self.build_failure_event(event, str(e))
                if isinstance(e, StepFailedError) and "metadata" in type(failure).model_fields:
                    metadata = {"stage": e.stage, "attempt": str(e.attempts), "attempts": str(e.attempts)}
                    failure = failure.model_copy(update={"metadata": {**(failure.metadata or {}), **metadata}})
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
