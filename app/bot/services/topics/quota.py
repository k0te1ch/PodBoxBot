"""Сколько тем один слушатель может предложить за сутки.

Счётчик на пару «автор + дата» живёт двое суток и дальше исчезает сам.
Лимит отдельно от хранилища тем: антиспам уедет в контур безопасности SDK.
"""

from datetime import datetime, tzinfo
from typing import Any

KEY_TTL_SECONDS = 2 * 24 * 3600


class DailyQuota:
    def __init__(self, redis: Any, limit: int, tz: tzinfo, namespace: str = "topics:quota") -> None:
        """*limit* 0 или меньше снимает ограничение."""
        self._redis = redis
        self.limit = limit
        self.tz = tz
        self.namespace = namespace

    def _key(self, user_id: int) -> str:
        return f"{self.namespace}:{user_id}:{datetime.now(self.tz):%Y%m%d}"

    async def take(self, user_id: int) -> bool:
        """Списать одну тему; ``False``, если лимит на сегодня исчерпан."""
        if self.limit <= 0:
            return True
        key = self._key(user_id)
        used = int(await self._redis.incr(key))
        if used == 1:
            await self._redis.expire(key, KEY_TTL_SECONDS)
        return used <= self.limit

    async def give_back(self, user_id: int) -> None:
        """Вернуть списанное, если тема в итоге не сохранилась."""
        if self.limit > 0:
            await self._redis.decr(self._key(user_id))
