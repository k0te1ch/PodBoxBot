"""Где табло публикации переживает перезапуск бота: Redis.

Publisher может ответить через минуту, а может через час: если бот за это
время перезапустили, событие должно найти своё табло и поправить в нём
строку, а не затереть таблицу одной строкой текста.

Ключи (``<ns>`` по умолчанию ``publish``):

* ``<ns>:board:<chat>:<ref>``: табло целиком в JSON. ``ref`` это id сообщения,
  которое бот отправил первым: его publisher'ы возвращают в событиях;
* ``<ns>:audio:<chat>:<audio>``: ``ref`` табло готового файла, чтобы вторая
  кнопка под тем же файлом дописала строку в то же табло;
* ``<ns>:recent``: упорядоченное множество ``<chat>:<ref>`` по времени
  последней записи, для ``/status``.

Всё живёт :data:`TTL_SECONDS` с последней записи. Без Redis и при его сбое
хранилище молчит: табло остаётся только в памяти процесса, как раньше.
"""

import json
import time
from collections.abc import Callable
from typing import Any

from loguru import logger

from services.none_module import _NoneModule

TTL_SECONDS = 30 * 24 * 3600
"""Сколько помнить табло после последнего события: 30 дней. Отложенный пост
выходит в пределах пары недель, позже событий по публикации уже не бывает."""
RECENT_LIMIT = 64


class BoardStore:
    def __init__(self, redis: Any, namespace: str = "publish", clock: Callable[[], float] = time.time) -> None:
        self._redis = redis
        self.namespace = namespace
        self._clock = clock

    @property
    def available(self) -> bool:
        return self._redis is not None and not isinstance(self._redis, _NoneModule)

    def _board_key(self, chat_id: object, ref_id: object) -> str:
        return f"{self.namespace}:board:{chat_id}:{ref_id}"

    def _audio_key(self, chat_id: object, audio_id: object) -> str:
        return f"{self.namespace}:audio:{chat_id}:{audio_id}"

    def _recent_key(self) -> str:
        return f"{self.namespace}:recent"

    async def save(self, data: dict) -> None:
        """Записать табло; сбой Redis не должен ронять публикацию."""
        if not self.available:
            return
        chat_id, ref_id = data["chat_id"], data["ref_id"]
        now = self._clock()
        try:
            await self._redis.set(self._board_key(chat_id, ref_id), json.dumps(data), ex=TTL_SECONDS)
            if data.get("audio_id") is not None:
                await self._redis.set(self._audio_key(chat_id, data["audio_id"]), str(ref_id), ex=TTL_SECONDS)
            recent = self._recent_key()
            await self._redis.zadd(recent, {f"{chat_id}:{ref_id}": now})
            await self._redis.zremrangebyscore(recent, "-inf", now - TTL_SECONDS)
            await self._redis.zremrangebyrank(recent, 0, -RECENT_LIMIT - 1)
        except Exception as error:
            logger.warning(f"publish board was not saved: {error!r}")

    async def load(self, chat_id: object, ref_id: object) -> dict | None:
        if not self.available:
            return None
        try:
            raw = await self._redis.get(self._board_key(chat_id, ref_id))
            return json.loads(raw) if raw else None
        except Exception as error:
            logger.warning(f"publish board was not loaded: {error!r}")
            return None

    async def ref_of_audio(self, chat_id: object, audio_id: object) -> str | None:
        """``ref`` табло, которое уже открыто под этим готовым файлом."""
        if not self.available:
            return None
        try:
            return await self._redis.get(self._audio_key(chat_id, audio_id))
        except Exception as error:
            logger.warning(f"publish board of the file was not found: {error!r}")
            return None

    async def recent(self, limit: int) -> list[tuple[str, str]] | None:
        """Адреса последних табло, от новых к старым; ``None`` без Redis."""
        if not self.available:
            return None
        try:
            members = await self._redis.zrevrange(self._recent_key(), 0, limit - 1)
        except Exception as error:
            logger.warning(f"recent publish boards were not listed: {error!r}")
            return None
        return [tuple(member.rsplit(":", 1)) for member in members]
