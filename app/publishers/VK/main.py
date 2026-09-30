"""VK publisher: подписан на publisher.vk.upload, публикует послешоу постом
VK Donut на стене сообщества (только для донов), шлёт result в
publisher.vk.result.

Уровень интеграции — официальный VK API (см. vk_client): звук уходит
видеозаписью с обложкой или документом, замок — ``donut_paid_duration``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os

from admin_alert import AdminAlerts
from loguru import logger
from vk_auth import VkAuth, VkAuthError
from vk_client import VkClient

from shared.config import config
from shared.kafka.models.paywalled_event import VkEvent
from shared.publishers.paywalled import PaywalledPublisher, handle_with
from shared.publishers.post_text import plain_text

_DAY = 24 * 3600


def _build_client() -> tuple[VkClient, VkAuth | None]:
    """Собирает клиента под выбранный режим доступа.

    ``token`` (по умолчанию) — статичный ключ, поведение как раньше.
    ``vkid`` — самообновляемая пара токенов VK ID: клиент берёт свежий
    access_token у :class:`VkAuth` перед каждым вызовом.
    """
    if config.VK_AUTH_MODE == "vkid":
        auth = VkAuth(
            config.VK_CLIENT_ID,
            config.VK_AUTH_FILE,
            client_secret=config.VK_CLIENT_SECRET,
            redirect_uri=config.VK_REDIRECT_URI,
        )
        client = VkClient(
            None,
            config.VK_GROUP_ID,
            config.VK_API_VERSION,
            token_provider=auth.access_token,
        )
        return client, auth
    return VkClient(config.VK_ACCESS_TOKEN, config.VK_GROUP_ID, config.VK_API_VERSION), None


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
        self.client, self.auth = _build_client()
        self.alerts = AdminAlerts(config.TELEGRAM_API_TOKEN, config.ADMINS_ID)
        self._maintenance_task: asyncio.Task | None = None

    async def _ensure_auth(self) -> None:  # type: ignore[override]
        self.client.check_config()
        if self.auth is not None:
            # Обновит пару токенов заранее, если access скоро истечёт; протухший
            # refresh поднимет VkAuthError (PermanentError) — публикация не
            # ретраится, админам уходит предупреждение с ссылкой на вход.
            try:
                await self.auth.access_token()
            except VkAuthError as e:
                await self._warn_reauth(str(e))
                raise

    async def _warn_reauth(self, reason: str) -> None:
        """Просит админов войти заново и, если можем, прикладывает ссылку входа."""
        link = self._authorize_hint()
        text = f"VK Donut: доступ слетел. {reason}"
        if link:
            text += f"\n\nВосстановить доступ: откройте ссылку, нажмите «Разрешить» и передайте код.\n{link}"
        await self.alerts.send("vk-reauth", text)

    def _authorize_hint(self) -> str | None:
        """Готовая ссылка авторизации VK ID, если приложение настроено."""
        if not (config.VK_CLIENT_ID and config.VK_REDIRECT_URI):
            return None
        from vk_auth import authorize_url, make_pkce

        _verifier, challenge = make_pkce()
        # code_verifier здесь не сохраняем: ссылка нужна как подсказка «куда
        # нажать»; сам обмен кода делает `smoke.py exchange`, который генерирует
        # свою пару PKCE. Точная инструкция — в SMOKE.md и гайде.
        return authorize_url(
            config.VK_CLIENT_ID,
            config.VK_REDIRECT_URI,
            challenge,
            "podboxbot",
            config.VK_SCOPE,
        )

    async def _maintenance_loop(self) -> None:
        """Держит доступ живым: обновляет пару и предупреждает до истечения.

        Между публикациями могут проходить недели, а access живёт час — без
        этого цикла первая же публикация после паузы стартовала бы с обновления
        по 401. Заодно ловим приближение конца срока refresh_token (180 дней) и
        предупреждаем админов заранее, пока доступ ещё рабочий.
        """
        interval = max(config.VK_MAINTENANCE_INTERVAL_HOURS, 0.5) * 3600
        while True:
            await asyncio.sleep(interval)
            if self.auth is None:
                continue
            try:
                await self.auth.refresh()
                await self._check_refresh_deadline()
                self.alerts.forget("vk-")
            except VkAuthError as e:
                await self._warn_reauth(str(e))
            except Exception as e:
                # Фоновый цикл не должен падать из-за разовой сетевой ошибки.
                logger.warning(f"VK maintenance cycle failed: {type(e).__name__}: {e}")

    async def _check_refresh_deadline(self) -> None:
        """Если refresh_token скоро истечёт — предупредить админов заранее."""
        status = await self.auth.status()
        left = status.refresh_seconds_left()
        if left is None:
            return
        if left <= config.VK_REFRESH_WARN_DAYS * _DAY:
            days = max(left // _DAY, 0)
            link = self._authorize_hint()
            text = (
                f"VK Donut: доступ надо продлить примерно через {days} дн. Пока всё работает, но лучше войти заранее."
            )
            if link:
                text += f"\n\nПродлить: откройте ссылку, нажмите «Разрешить» и передайте код.\n{link}"
            await self.alerts.send("vk-refresh-deadline", text)

    async def publish_post(self, event: VkEvent) -> tuple[str, str]:  # type: ignore[override]
        path = event.path or ""
        text = plain_text(event.comment, event.chapters)
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
                    event,
                    "upload_doc",
                    lambda: self.client.upload_doc(path, os.path.basename(path)),
                )
            )

        message = f"{event.title}\n\n{text}".strip()
        post_id = await self.call_with_retry(
            event,
            "publish",
            lambda: self.client.post(message, attachments, self.donut_paid_duration),
        )
        return post_id, self.client.post_url(post_id)

    async def fetch_post(self, post_id: str) -> dict | None:
        return await self.client.get_post(post_id)

    async def run(self) -> None:  # type: ignore[override]
        """Consumer-цикл + фоновое обслуживание доступа VK ID (только режим vkid)."""
        if self.auth is not None:
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        try:
            await super().run()
        finally:
            if self._maintenance_task is not None:
                self._maintenance_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._maintenance_task


_publisher = VkPublisher()


async def handle_upload(payload: dict, producer=None) -> None:
    await handle_with(_publisher, payload, producer)


if __name__ == "__main__":
    asyncio.run(_publisher.run())
