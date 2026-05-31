"""Boosty publisher: подписан на publisher.boosty.upload, публикует aftershow-
эпизод на Boosty (текст + прикреплённый mp3 + обложка-тизер) на платном уровне
подписки, шлёт result в publisher.boosty.result.

Флоу публикации (реверс из трафика редактора, см. boosty_client + спайк):
получить container_id → загрузить mp3 → загрузить обложку → опубликовать пост
с `subscription_level_id` (платный уровень) + `price` (pay-per-post).

Boosty — только для aftershow: бот шлёт сюда событие лишь из postshow-меню,
уровень/цена фиксированы конфигом (BOOSTY_SUBSCRIPTION_LEVEL_ID/BOOSTY_PRICE).
"""

from __future__ import annotations

import asyncio
import os

from boosty_client import BoostyClient
from loguru import logger

from shared.config import config
from shared.kafka.models.boosty_event import BoostyEvent
from shared.kafka.producer import KafkaProducer
from shared.publishers.base import BasePublisher

# Boosty-config — берётся только тут, base про эти переменные не знает.
BOOSTY_BLOG = config.BOOSTY_BLOG
BOOSTY_AUTH_FILE = config.BOOSTY_AUTH_FILE
BOOSTY_SUBSCRIPTION_LEVEL_ID = config.BOOSTY_SUBSCRIPTION_LEVEL_ID
BOOSTY_PRICE = config.BOOSTY_PRICE
BOOSTY_COVER_PATH = config.BOOSTY_COVER_PATH
BOOSTY_ADVERTISER_INFO = config.BOOSTY_ADVERTISER_INFO

_REFRESH_INTERVAL = 3600  # сек — ежечасный прогрев сессии (access/refresh)


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

    async def publish(self, event: BoostyEvent) -> None:  # type: ignore[override]
        if not event.path:
            raise RuntimeError("BoostyEvent.path (mp3 file) is required for Boosty publish")
        if not BOOSTY_SUBSCRIPTION_LEVEL_ID:
            raise RuntimeError("BOOSTY_SUBSCRIPTION_LEVEL_ID is not configured")

        container_id = await self.client.get_container_id()
        audio_id, audio_size = await self.client.upload_audio(event.path, container_id)
        cover_id = await self.client.upload_image(BOOSTY_COVER_PATH)

        post_id = await self.client.publish(
            title=event.title,
            body=event.comment,
            chapters=event.chapters,
            audio_id=audio_id,
            audio_size=audio_size,
            audio_title=os.path.basename(event.path),
            cover_id=cover_id,
            subscription_level_id=BOOSTY_SUBSCRIPTION_LEVEL_ID,
            price=BOOSTY_PRICE,
            advertiser_info=BOOSTY_ADVERTISER_INFO,
        )

        result = event.model_copy(
            update={
                "event_type": "result",
                "status": "success",
                "post_id": post_id,
            }
        )
        await self.producer.send(self.result_topic, result.model_dump())
        logger.success(f"Boosty publish completed for episode {event.number} (post_id={post_id or '?'})")

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

    async def _refresh_loop(self) -> None:
        """Ежечасно прогревает сессию: либа рефрешит токен только по 401,
        а долгие простои между публикациями могут пережить истечение."""
        while True:
            await asyncio.sleep(_REFRESH_INTERVAL)
            try:
                await self.client.refresh()
            except Exception as e:
                logger.warning(f"Boosty hourly token refresh failed: {e!r}")

    async def run(self) -> None:  # type: ignore[override]
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        await super().run()


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
