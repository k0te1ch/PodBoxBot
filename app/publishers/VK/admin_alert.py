"""Сообщения админам в Telegram напрямую из publisher'а.

Бот сообщает о публикации через result-топик, но предупреждение «доступ VK
скоро кончится» не привязано ни к какой публикации: его шлёт фоновая проверка
доступа. Поэтому publisher пишет админам сам, через Bot API тем же токеном
бота (``TELEGRAM_API_TOKEN``), что и алерты Grafana.

Одинаковые предупреждения не повторяются чаще ``repeat_after`` секунд: ключ
предупреждения и время отправки лежат в памяти процесса, после рестарта
контейнера актуальное предупреждение придёт ещё раз, и это нормально.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

import httpx
from loguru import logger

TELEGRAM_API = "https://api.telegram.org"


class AdminAlerts:
    def __init__(
        self,
        bot_token: str | None,
        chat_ids: Iterable[int],
        *,
        repeat_after: float = 24 * 3600,
        http: httpx.AsyncClient | None = None,
        clock=time.time,
    ) -> None:
        self.bot_token = bot_token
        self.chat_ids = [chat_id for chat_id in chat_ids if chat_id]
        self.repeat_after = repeat_after
        self.http = http or httpx.AsyncClient(timeout=30)
        self.clock = clock
        self._sent: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_ids)

    async def send(self, key: str, text: str) -> bool:
        """Шлёт ``text`` всем админам, если ``key`` не отправлялся недавно.

        Возвращает True, если сообщение ушло хотя бы одному админу. Ошибка
        Telegram не роняет проверку доступа: она только пишется в лог.
        """
        now = self.clock()
        last = self._sent.get(key)
        if last is not None and now - last < self.repeat_after:
            return False
        if not self.enabled:
            logger.warning(f"VK access alert not sent (no TELEGRAM_API_TOKEN or ADMINS_ID): {text}")
            return False
        delivered = False
        for chat_id in self.chat_ids:
            try:
                resp = await self.http.post(
                    f"{TELEGRAM_API}/bot{self.bot_token}/sendMessage",
                    data={
                        "chat_id": chat_id,
                        "text": text,
                        "disable_web_page_preview": "true",
                    },
                )
                resp.raise_for_status()
                delivered = True
            except httpx.HTTPError as e:
                logger.error(f"VK access alert to {chat_id} failed: {type(e).__name__}")
        if delivered:
            self._sent[key] = now
        return delivered

    def forget(self, key_prefix: str = "") -> None:
        """Сбрасывает память об отправленных предупреждениях (доступ восстановлен)."""
        for key in [k for k in self._sent if k.startswith(key_prefix)]:
            del self._sent[key]
