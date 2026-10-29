"""Sponsr publisher: подписан на publisher.sponsr.upload, публикует послешоу
для подписчиков проекта, шлёт result в publisher.sponsr.result.

Уровень интеграции: запросы веб-редактора по куке SESS (см. sponsr_client),
сверенные с записью ручной публикации.
"""

from __future__ import annotations

import asyncio

from sponsr_client import SponsrClient

from shared.config import config
from shared.kafka.models.paywalled_event import SponsrEvent
from shared.publishers.paywalled import PaywalledPublisher, handle_with
from shared.publishers.post_text import html_text


class SponsrPublisher(PaywalledPublisher):
    name = "sponsr"
    event_cls = SponsrEvent
    schema_path = "/app/shared/kafka/schemas/sponsr_event.avsc"
    upload_topic = config.SPONSR_UPLOAD_TOPIC
    result_topic = config.SPONSR_RESULT_TOPIC
    group_id = "sponsr_group"

    retry_attempts = config.SPONSR_RETRY_ATTEMPTS
    retry_backoff = config.SPONSR_RETRY_BACKOFF

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.client = SponsrClient(config.SPONSR_SESSION_FILE, config.SPONSR_PROJECT, config.SPONSR_LEVEL_ID)

    async def _ensure_auth(self) -> None:  # type: ignore[override]
        await self.client.ensure_auth()

    async def publish_post(self, event: SponsrEvent) -> tuple[str, str]:  # type: ignore[override]
        path = event.path or ""
        post_id = await self.call_with_retry(
            event,
            "publish",
            lambda: self.client.publish(
                title=event.title,
                content=html_text(event.comment, event.chapters),
                teaser=(event.comment or "").strip().split("\n")[0],
                path=path,
            ),
        )
        return post_id, self.client.post_url(post_id)

    async def fetch_post(self, post_id: str) -> dict | None:
        return await self.client.get_post(post_id)


_publisher = SponsrPublisher()


async def handle_upload(payload: dict, producer=None) -> None:
    await handle_with(_publisher, payload, producer)


if __name__ == "__main__":
    asyncio.run(_publisher.run())
