"""WordPress publisher: подписан на publisher.wordpress.upload, публикует
эпизод через wp-admin форму + Podlove REST, шлёт result в
publisher.wordpress.result."""
from __future__ import annotations

import asyncio

from loguru import logger
from wordpress import WordPress

from shared.config import config
from shared.kafka.models.wordpress_event import WordPressEvent
from shared.kafka.producer import KafkaProducer
from shared.publishers.base import BasePublisher

# WordPress-config — берётся только тут, base про эти переменные не знает.
WP_URL = config.WP_URL
WP_LOGIN = config.WP_LOGIN
WP_PASSWORD = config.WP_PASSWORD
WP_APP_PASSWORD = config.WP_APP_PASSWORD
WP_COOKIE_PATH = config.WP_COOKIE_PATH
TIMEZONE = config.TIMEZONE


class WordPressPublisher(BasePublisher):
    name = "wp"
    event_cls = WordPressEvent
    schema_path = "/app/shared/kafka/schemas/wordpress_event.avsc"
    upload_topic = config.WP_UPLOAD_TOPIC
    result_topic = config.WP_RESULT_TOPIC
    group_id = "wordpress_group"

    async def publish(self, event: WordPressEvent) -> None:  # type: ignore[override]
        info = {
            "number": event.number,
            "title": event.title,
            "comment": event.comment,
            "chapters": event.chapters,
            "tags": event.tags,
            "slug": event.slug,
            "duration": event.duration,
        }

        # WordPress.upload_post() — синхронный (requests-based). Запускаем
        # в default executor через to_thread, чтобы не блокировать event loop.
        def _run() -> bool:
            with WordPress(
                WP_URL, WP_LOGIN, WP_PASSWORD, WP_APP_PASSWORD, WP_COOKIE_PATH, TIMEZONE
            ) as wp:
                return wp.upload_post(info)

        success = await asyncio.to_thread(_run)

        if not success:
            # base.py поймает и сконвертирует в failure-event
            raise RuntimeError("WordPress returned non-success response")

        result = event.model_copy(update={"event_type": "result", "status": "success"})
        await self.producer.send(self.result_topic, result.model_dump())
        logger.success(f"WordPress upload completed for episode {event.number}")

    def event_key(self, event: WordPressEvent) -> str:  # type: ignore[override]
        return event.number

    def build_failure_event(self, event: WordPressEvent, error: str):  # type: ignore[override]
        # Echo all event fields, переписав status/error/event_type.
        return event.model_copy(
            update={
                "event_type": "result",
                "status": "failure",
                "error": error,
            }
        )


_publisher = WordPressPublisher()


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
