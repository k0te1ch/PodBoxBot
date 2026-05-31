"""Boosty publisher: подписан на publisher.boosty.upload, создаёт пост на
Boosty через internal-API с привязкой к уровню подписки (paywall/tier),
шлёт result в publisher.boosty.result.

Tier-логика (см. BasePublisher.is_paywalled + спайк):
* `paywall_tier` на событии (имя уровня или id) — высший приоритет;
* иначе aftershow → платный уровень `BOOSTY_AFTERSHOW_LEVEL`,
  main/прочее → бесплатный уровень `BOOSTY_FREE_LEVEL`.
"""

from __future__ import annotations

import asyncio

from boosty_client import BoostyClient
from loguru import logger

from shared.config import config
from shared.kafka.models.boosty_event import BoostyEvent
from shared.kafka.producer import KafkaProducer
from shared.publishers.base import BasePublisher

# Boosty-config — берётся только тут, base про эти переменные не знает.
BOOSTY_BLOG = config.BOOSTY_BLOG
BOOSTY_AUTH_FILE = config.BOOSTY_AUTH_FILE
BOOSTY_AFTERSHOW_LEVEL = config.BOOSTY_AFTERSHOW_LEVEL
BOOSTY_FREE_LEVEL = config.BOOSTY_FREE_LEVEL


class BoostyPublisher(BasePublisher):
    name = "boosty"
    event_cls = BoostyEvent
    schema_path = "/app/shared/kafka/schemas/boosty_event.avsc"
    upload_topic = config.BOOSTY_UPLOAD_TOPIC
    result_topic = config.BOOSTY_RESULT_TOPIC
    group_id = "boosty_group"

    supports_paywall = True
    supports_scheduled = False

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.client = BoostyClient(BOOSTY_BLOG or "", BOOSTY_AUTH_FILE)

    async def _ensure_auth(self) -> None:  # type: ignore[override]
        await self.client.ensure_auth()

    def _target_level(self, event: BoostyEvent) -> str:
        """Имя/id уровня подписки для события.

        paywall_tier приоритетен; иначе — дефолт по платности (is_paywalled).
        """
        if event.paywall_tier:
            return event.paywall_tier
        if self.is_paywalled(event):
            if not BOOSTY_AFTERSHOW_LEVEL:
                raise RuntimeError("Paid episode but BOOSTY_AFTERSHOW_LEVEL is not configured")
            return BOOSTY_AFTERSHOW_LEVEL
        if not BOOSTY_FREE_LEVEL:
            raise RuntimeError("Public episode but BOOSTY_FREE_LEVEL is not configured")
        return BOOSTY_FREE_LEVEL

    async def publish(self, event: BoostyEvent) -> None:  # type: ignore[override]
        level_id = await self.client.resolve_level_id(self._target_level(event))

        post_id = await self.client.create_post(
            title=event.title,
            body=event.comment,
            subscription_level_id=level_id,
            chapters=event.chapters,
            tags=",".join(event.tags),
        )

        result = event.model_copy(
            update={
                "event_type": "result",
                "status": "success",
                "post_id": post_id,
            }
        )
        await self.producer.send(self.result_topic, result.model_dump())
        logger.success(
            f"Boosty upload completed for episode {event.number} (level={level_id}, post_id={post_id or '?'})"
        )

    def event_key(self, event: BoostyEvent) -> str:  # type: ignore[override]
        return event.number

    def build_failure_event(self, event: BoostyEvent, error: str):  # type: ignore[override]
        return event.model_copy(
            update={
                "event_type": "result",
                "status": "failure",
                "error": error,
            }
        )


_publisher = BoostyPublisher()


async def handle_upload(payload: dict, producer: KafkaProducer | None = None) -> None:
    """Test-compat shim. См. подробности в FTP/main.py.handle_upload."""
    if producer is not None:
        original = _publisher.producer
        _publisher.producer = producer
        try:
            await _publisher._handle(payload)
        finally:
            _publisher.producer = original
    else:
        await _publisher._handle(payload)


if __name__ == "__main__":
    asyncio.run(_publisher.run())
