"""Boosty publisher: подписан на publisher.boosty.upload, публикует aftershow-
эпизод на Boosty (текст + прикреплённый mp3 + обложка-тизер) на платном уровне
подписки, шлёт result в publisher.boosty.result.

Флоу публикации (реверс из трафика редактора, см. boosty_client + спайк):
получить container_id → загрузить mp3 → загрузить обложку → опубликовать пост
с `subscription_level_id` (платный уровень) + `price` (pay-per-post).

BOOSTY_PUBLISH_MODE выбирает последний шаг: `publish` (по умолчанию, сразу
подписчикам), `draft` (черновик в редакторе блога, публикует автор) или
`scheduled` (отложенный пост через BOOSTY_SCHEDULE_DELAY_HOURS часов).

Boosty — только для aftershow: бот шлёт сюда событие лишь из postshow-меню,
уровень/цена фиксированы конфигом (BOOSTY_SUBSCRIPTION_LEVEL_ID/BOOSTY_PRICE).

Протухшая авторизация — BoostyAuthError (PermanentError): шаг не повторяется,
админ сразу получает текст с инструкцией. Живой смоук — SMOKE.md.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from boosty_client import BoostyClient, BoostyPublishedNowError, PostContent
from loguru import logger

from shared.config import config
from shared.kafka.models.boosty_event import BoostyEvent
from shared.kafka.producer import KafkaProducer
from shared.publishers.base import BasePublisher

# Boosty-config — берётся только тут, base про эти переменные не знает.
BOOSTY_BLOG = config.BOOSTY_BLOG
BOOSTY_AUTH_FILE = config.BOOSTY_AUTH_FILE
BOOSTY_OWNER_ID = config.BOOSTY_OWNER_ID
BOOSTY_SUBSCRIPTION_LEVEL_ID = config.BOOSTY_SUBSCRIPTION_LEVEL_ID
BOOSTY_PRICE = config.BOOSTY_PRICE
BOOSTY_COVER_PATH = config.BOOSTY_COVER_PATH
BOOSTY_ADVERTISER_INFO = config.BOOSTY_ADVERTISER_INFO
BOOSTY_PUBLISH_MODE = config.BOOSTY_PUBLISH_MODE
BOOSTY_SCHEDULE_DELAY_HOURS = config.BOOSTY_SCHEDULE_DELAY_HOURS

_REFRESH_INTERVAL = 3600  # сек — ежечасный прогрев сессии (access/refresh)


def _local_time(timestamp: int) -> str:
    """Время отложенной публикации для статуса в боте, в TIMEZONE сервиса."""
    try:
        tz = ZoneInfo(config.TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        tz = UTC
    return datetime.fromtimestamp(timestamp, tz).strftime("%d.%m.%Y %H:%M %Z")


class BoostyPublisher(BasePublisher):
    name = "boosty"
    event_cls = BoostyEvent
    schema_path = "/app/shared/kafka/schemas/boosty_event.avsc"
    upload_topic = config.BOOSTY_UPLOAD_TOPIC
    result_topic = config.BOOSTY_RESULT_TOPIC
    group_id = "boosty_group"

    retry_attempts = config.BOOSTY_RETRY_ATTEMPTS
    retry_backoff = config.BOOSTY_RETRY_BACKOFF

    supports_paywall = True
    supports_scheduled = True

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

        # ownerId стабилен для блога; берём из конфига, иначе пробуем достать из
        # активного черновика (есть только если он создан в редакторе).
        path = event.path
        container_id = BOOSTY_OWNER_ID or await self.call_with_retry(event, "container", self.client.get_container_id)
        audio_id, audio_size = await self.call_with_retry(
            event, "upload_audio", lambda: self.client.upload_audio(path, container_id)
        )
        cover_id = await self.call_with_retry(
            event, "upload_image", lambda: self.client.upload_image(BOOSTY_COVER_PATH)
        )

        post = PostContent(
            title=event.title,
            body=event.comment,
            chapters=event.chapters,
            audio_id=audio_id,
            audio_size=audio_size,
            audio_title=os.path.basename(path),
            cover_id=cover_id,
            subscription_level_id=BOOSTY_SUBSCRIPTION_LEVEL_ID,
            price=BOOSTY_PRICE,
            advertiser_info=BOOSTY_ADVERTISER_INFO,
        )
        if BOOSTY_PUBLISH_MODE == "draft":
            await self._save_draft(event, post)
        elif BOOSTY_PUBLISH_MODE == "scheduled":
            await self._schedule(event, post)
        else:
            await self._publish_now(event, post)

    async def _publish_now(self, event: BoostyEvent, post: PostContent) -> None:
        """Режим publish: пост сразу виден подписчикам платного уровня."""
        post_id = await self.call_with_retry(event, "publish", lambda: self.client.publish(post))

        metadata = {"action": "published"}
        if post_id and BOOSTY_BLOG:
            # Страница поста — SPA и отвечает 200 на любой id, поэтому
            # проверяем через API: пост должен находиться по id.
            await self.call_with_retry(
                event,
                "verify",
                lambda: self._check_post(post_id),
                attempts=self.verify_attempts,
                backoff=self.verify_backoff,
            )
            metadata["url"] = f"https://boosty.to/{BOOSTY_BLOG}/posts/{post_id}"
        await self._send_success(event, post_id, metadata)

    async def _save_draft(self, event: BoostyEvent, post: PostContent) -> None:
        """Режим draft: пост остаётся черновиком в редакторе, подписчики его не видят."""
        await self.call_with_retry(event, "save_draft", lambda: self.client.save_draft(post))
        await self.call_with_retry(
            event,
            "verify",
            lambda: self._check_draft(post.title),
            attempts=self.verify_attempts,
            backoff=self.verify_backoff,
        )
        metadata = {"action": "draft"}
        if BOOSTY_BLOG:
            metadata["url"] = f"https://boosty.to/{BOOSTY_BLOG}/new-post"
        await self._send_success(event, "", metadata)

    async def _schedule(self, event: BoostyEvent, post: PostContent) -> None:
        """Режим scheduled: отложенный пост, подписчики увидят его в ``publish_time``."""
        publish_time = int(time.time() + BOOSTY_SCHEDULE_DELAY_HOURS * 3600)
        scheduled = await self.call_with_retry(event, "publish", lambda: self.client.schedule(post, publish_time))
        post_id = str(scheduled.get("id") or scheduled.get("int_id") or "")
        if post_id:
            await self.call_with_retry(
                event,
                "verify",
                lambda: self._check_post(post_id, published=False),
                attempts=self.verify_attempts,
                backoff=self.verify_backoff,
            )
        metadata = {"action": "scheduled", "publish_at": _local_time(publish_time)}
        if post_id and BOOSTY_BLOG:
            metadata["url"] = f"https://boosty.to/{BOOSTY_BLOG}/posts/{post_id}"
        await self._send_success(event, post_id, metadata)

    async def _send_success(self, event: BoostyEvent, post_id: str, metadata: dict[str, str]) -> None:
        result = event.model_copy(
            update={"event_type": "result", "status": "success", "post_id": post_id or None, "metadata": metadata}
        )
        await self.producer.send(self.result_topic, result.model_dump())
        logger.success(f"Boosty {metadata['action']} done for episode {event.number} (post_id={post_id or '-'})")

    async def _check_draft(self, title: str) -> None:
        draft = await self.client.get_draft()
        if not draft or draft.get("title") != title:
            raise RuntimeError(f"Boosty draft with title {title!r} not found after save")

    async def _check_post(self, post_id: str, *, published: bool = True) -> None:
        post = await self.client.get_post(post_id)
        if str(post.get("id") or "") != post_id or post.get("isDeleted"):
            raise RuntimeError(f"Boosty post {post_id} not found after publish: {post!r}")
        if not published and post.get("isPublished"):
            # Пост уже у подписчиков: повтор ничего не исправит.
            raise BoostyPublishedNowError(post_id)

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
        """Consumer-цикл + фоновый прогрев сессии.

        Прогрев живёт ровно столько же, сколько цикл: при остановке (отмена
        снаружи, падение consumer'а) таск гасится, иначе он переживает
        publisher и продолжает дёргать refresh уже никому не нужной сессии.
        """
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        try:
            await super().run()
        finally:
            self._refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._refresh_task


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
