"""VK publisher: подписан на publisher.vk.upload, публикует послешоу для донов
сообщества, шлёт result в publisher.vk.result.

Основной режим ``VK_MEDIA=podcast``: эпизод в разделе подкастов сообщества с
доступом «Только донам» и пост с ним на стене, по сессии vk.ru (см.
vk_podcast: у официального API нет загрузки подкастов). Запасные режимы
``video``, ``doc`` и ``none`` идут через официальный VK API (см. vk_client):
звук видеозаписью с обложкой или документом, замок ``donut_paid_duration``.
"""

from __future__ import annotations

import asyncio
import os

from vk_client import VkClient
from vk_podcast import VkPodcastClient

from shared.config import config
from shared.kafka.models.paywalled_event import VkEvent
from shared.publishers.paywalled import PaywalledPublisher, handle_with
from shared.publishers.post_text import plain_text


class VkPublisher(PaywalledPublisher):
    name = "vk"
    event_cls = VkEvent
    schema_path = "/app/shared/kafka/schemas/vk_event.avsc"
    upload_topic = config.VK_UPLOAD_TOPIC
    result_topic = config.VK_RESULT_TOPIC
    group_id = "vk_group"

    retry_attempts = config.VK_RETRY_ATTEMPTS
    retry_backoff = config.VK_RETRY_BACKOFF

    media = config.VK_MEDIA
    cover_path = config.VK_COVER_PATH
    donut_paid_duration = config.VK_DONUT_PAID_DURATION

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.client = VkClient(config.VK_ACCESS_TOKEN, config.VK_GROUP_ID, config.VK_API_VERSION)
        self.podcast = VkPodcastClient(
            config.VK_SESSION_FILE, config.VK_GROUP_ID, config.VK_PODCAST_PRIVACY, config.VK_PODCAST_COVER_ID
        )

    async def _ensure_auth(self) -> None:  # type: ignore[override]
        if self.media == "podcast":
            await self.podcast.web_token()
        else:
            self.client.check_config()

    async def publish_post(self, event: VkEvent) -> tuple[str, str]:  # type: ignore[override]
        path = event.path or ""
        text = plain_text(event.comment, event.chapters)
        message = f"{event.title}\n\n{text}".strip()
        if self.media == "podcast":
            attachment = await self.call_with_retry(
                event,
                "upload_episode",
                lambda: self.podcast.prepare_episode(path, title=event.title, desc=text),
            )
            post_id = await self.call_with_retry(event, "publish", lambda: self.podcast.post(message, attachment))
            return post_id, self.podcast.post_url(post_id)

        attachments: list[str] = []
        if self.media == "video":
            attachments.append(
                await self.call_with_retry(
                    event,
                    "upload_video",
                    lambda: self.client.upload_video(path, self.cover_path, event.title, text),
                )
            )
        elif self.media == "doc":
            attachments.append(
                await self.call_with_retry(
                    event, "upload_doc", lambda: self.client.upload_doc(path, os.path.basename(path))
                )
            )

        post_id = await self.call_with_retry(
            event, "publish", lambda: self.client.post(message, attachments, self.donut_paid_duration)
        )
        return post_id, self.client.post_url(post_id)

    async def fetch_post(self, post_id: str) -> dict | None:
        if self.media == "podcast":
            return await self.podcast.get_post(post_id)
        return await self.client.get_post(post_id)


_publisher = VkPublisher()


async def handle_upload(payload: dict, producer=None) -> None:
    await handle_with(_publisher, payload, producer)


if __name__ == "__main__":
    asyncio.run(_publisher.run())
