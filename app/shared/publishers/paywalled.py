"""Общая часть publisher'ов послешоу под замком (VK Donut, Patreon, Sponsr).

Подкласс реализует только :meth:`publish_post` — загрузку и публикацию на
своей площадке — и возвращает id поста и ссылку. База проверяет входные
данные, прогоняет проверку поста через :meth:`fetch_post` с повторами и
отправляет success-result в том же формате, что Boosty.
"""

from __future__ import annotations

from abc import abstractmethod

from loguru import logger

from shared.kafka.models.paywalled_event import PaywalledPostEvent
from shared.publishers.base import BasePublisher


class PaywalledPublisher(BasePublisher):
    supports_paywall = True
    supports_scheduled = False

    @abstractmethod
    async def publish_post(self, event: PaywalledPostEvent) -> tuple[str, str]:
        """Публикует пост; возвращает (post_id, url)."""

    @abstractmethod
    async def fetch_post(self, post_id: str) -> dict | None:
        """Читает пост с площадки; None — поста нет."""

    async def _check_post(self, post_id: str) -> None:
        if not await self.fetch_post(post_id):
            raise RuntimeError(f"{self.name} post {post_id} not found after publish")

    async def publish(self, event: PaywalledPostEvent) -> None:  # type: ignore[override]
        if not event.path:
            raise RuntimeError(f"{type(event).__name__}.path (mp3 file) is required")

        post_id, url = await self.publish_post(event)
        await self.call_with_retry(
            event,
            "verify",
            lambda: self._check_post(post_id),
            attempts=self.verify_attempts,
            backoff=self.verify_backoff,
        )

        result = event.model_copy(
            update={
                "event_type": "result",
                "status": "success",
                "post_id": post_id,
                "metadata": self.success_metadata(url=url),
            }
        )
        await self.producer.send(self.result_topic, result.model_dump())
        logger.success(f"{self.name} publish completed for episode {event.number} ({url})")

    def event_key(self, event: PaywalledPostEvent) -> str:  # type: ignore[override]
        return event.number


async def handle_with(publisher: BasePublisher, payload: dict, producer=None) -> None:
    """Прогон одного события с подменой producer — точка входа тестов."""
    if producer is None:
        await publisher._handle(payload)
        return
    original = publisher.producer
    publisher.producer = producer
    try:
        await publisher._handle(payload)
    finally:
        publisher.producer = original
