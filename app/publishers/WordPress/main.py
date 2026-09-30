"""WordPress publisher: подписан на publisher.wordpress.upload, публикует
эпизод через wp-admin форму + Podlove REST, шлёт result в
publisher.wordpress.result."""

from __future__ import annotations

import asyncio

import aiohttp
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
WP_VERIFY = config.WP_VERIFY


class WordPressPublisher(BasePublisher):
    name = "wp"
    event_cls = WordPressEvent
    schema_path = "/app/shared/kafka/schemas/wordpress_event.avsc"
    upload_topic = config.WP_UPLOAD_TOPIC
    result_topic = config.WP_RESULT_TOPIC
    group_id = "wordpress_group"
    retry_attempts = config.WP_RETRY_ATTEMPTS
    retry_backoff = config.WP_RETRY_BACKOFF
    # Пост уходит на сайт черновиком, публикует его редактор вручную.
    publish_action = "draft"

    async def publish(self, event: WordPressEvent) -> None:  # type: ignore[override]
        info = {
            "number": event.number,
            "title": event.title,
            "comment": event.comment,
            "chapters": event.chapters,
            "tags": event.tags,
            "slug": event.slug,
            "duration": event.duration,
            "recording_date": event.recording_date,
        }

        # WordPress.upload_post() — синхронный (requests-based). Запускаем
        # в default executor через to_thread, чтобы не блокировать event loop.
        def _run() -> tuple[str | None, str | None]:
            with WordPress(WP_URL, WP_LOGIN, WP_PASSWORD, WP_APP_PASSWORD, WP_COOKIE_PATH, TIMEZONE) as wp:
                if not wp.upload_post(info):
                    raise RuntimeError("WordPress returned non-success response")
                post_id = wp.last_post_id
                rest_path = wp.podcast_rest_path(post_id) if post_id and WP_VERIFY else None
                return post_id, rest_path

        post_id, rest_path = await self.call_with_retry(event, "publish", lambda: asyncio.to_thread(_run))

        metadata = self.success_metadata()
        if post_id:
            metadata["post_id"] = post_id
            if WP_VERIFY:
                path = rest_path if isinstance(rest_path, str) else f"/wp/v2/episodes/{post_id}"
                metadata["url"] = await self._verify_draft(event, path)

        result = event.model_copy(update={"event_type": "result", "status": "success", "metadata": metadata})
        await self.producer.send(self.result_topic, result.model_dump())
        logger.success(f"WordPress upload completed for episode {event.number}")

    async def _verify_draft(self, event: WordPressEvent, rest_path: str) -> str:
        """Пост сохраняется черновиком, публично его не видно — проверяем
        через REST под Application Password, что черновик действительно есть."""
        url = f"{(WP_URL or '').rstrip('/')}/wp-json{rest_path}?context=edit"
        auth = aiohttp.BasicAuth(WP_LOGIN or "", WP_APP_PASSWORD) if WP_APP_PASSWORD else None
        async with aiohttp.ClientSession(auth=auth) as session:
            await self.verify(event, url, session=session)
        return url

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
