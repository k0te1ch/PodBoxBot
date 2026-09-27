"""Patreon publisher: подписан на publisher.patreon.upload, публикует послешоу
аудиопостом для платных патронов, шлёт result в publisher.patreon.result.

Уровень интеграции — запросы веб-редактора по сессионной куке (см.
patreon_client: официальный API v2 создавать посты не умеет).
"""

from __future__ import annotations

import asyncio

from patreon_client import PatreonClient

from shared.config import config
from shared.kafka.models.paywalled_event import PatreonEvent
from shared.publishers.paywalled import PaywalledPublisher, handle_with
from shared.publishers.post_text import html_text


class PatreonPublisher(PaywalledPublisher):
    name = "patreon"
    event_cls = PatreonEvent
    schema_path = "/app/shared/kafka/schemas/patreon_event.avsc"
    upload_topic = config.PATREON_UPLOAD_TOPIC
    result_topic = config.PATREON_RESULT_TOPIC
    group_id = "patreon_group"

    retry_attempts = config.PATREON_RETRY_ATTEMPTS
    retry_backoff = config.PATREON_RETRY_BACKOFF

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.client = PatreonClient(config.PATREON_SESSION_FILE, config.PATREON_TIER_IDS)

    async def _ensure_auth(self) -> None:  # type: ignore[override]
        await self.client.ensure_auth()

    async def publish_post(self, event: PatreonEvent) -> tuple[str, str]:  # type: ignore[override]
        path = event.path or ""
        rule_ids = await self.call_with_retry(event, "access_rules", self.client.access_rules)
        post_id = await self.call_with_retry(event, "create_draft", self.client.create_draft)
        await self.call_with_retry(event, "upload_audio", lambda: self.client.upload_audio(post_id, path))
        await self.call_with_retry(
            event,
            "publish",
            lambda: self.client.publish(
                post_id,
                title=event.title,
                content=html_text(event.comment, event.chapters),
                teaser=(event.comment or "").split("\n")[0],
                rule_ids=rule_ids,
            ),
        )
        return post_id, self.client.post_url(post_id)

    async def fetch_post(self, post_id: str) -> dict | None:
        return await self.client.get_post(post_id)


_publisher = PatreonPublisher()


async def handle_upload(payload: dict, producer=None) -> None:
    await handle_with(_publisher, payload, producer)


if __name__ == "__main__":
    asyncio.run(_publisher.run())
