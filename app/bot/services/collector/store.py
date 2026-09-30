"""Хранилище записей в Redis.

Раскладка ключей для коллекции ``ns``:

* ``ns:seq`` — счётчик id;
* ``ns:e:<id>`` — запись в JSON;
* ``ns:t:<tag>`` — sorted set неиспользованных записей группы (score — время);
* ``ns:used`` — sorted set отмеченных «использовано»;
* ``ns:m:<chat>:<message>`` — метка, что сообщение уже собрано.

Группы — это хештеги: список по группе читается одним ZREVRANGE, поэтому
большие объёмы не смешиваются и не грузятся целиком.
"""

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

# Сколько последних записей группы отдавать в меню. Старше — всё ещё в Redis,
# но листать сотни страниц кнопок бессмысленно.
DEFAULT_LIST_LIMIT = 200


@dataclass
class Entry:
    tag: str
    text: str
    author: str
    id: int = 0
    created_at: float = field(default_factory=time.time)
    link: str | None = None
    used: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "Entry":
        return cls(**json.loads(raw))


class EntryStore:
    def __init__(self, redis: Any, namespace: str, list_limit: int = DEFAULT_LIST_LIMIT) -> None:
        self._redis = redis
        self.namespace = namespace
        self.list_limit = list_limit

    def _key(self, *parts: object) -> str:
        return ":".join((self.namespace, *map(str, parts)))

    async def add(self, entry: Entry, source: tuple[int, int] | None = None) -> Entry | None:
        """Сохранить запись; *source* (chat_id, message_id) защищает от повторов."""
        if source is not None:
            fresh = await self._redis.set(self._key("m", *source), 1, nx=True)
            if not fresh:
                return None
        entry.id = int(await self._redis.incr(self._key("seq")))
        await self._redis.set(self._key("e", entry.id), entry.to_json())
        await self._redis.zadd(self._key("t", entry.tag), {str(entry.id): entry.created_at})
        return entry

    async def get(self, entry_id: int) -> Entry | None:
        raw = await self._redis.get(self._key("e", entry_id))
        return Entry.from_json(raw) if raw else None

    async def list(self, tag: str) -> list[Entry]:
        """Неиспользованные записи группы, свежие сверху."""
        ids = await self._redis.zrevrange(self._key("t", tag), 0, self.list_limit - 1)
        entries = [await self.get(int(entry_id)) for entry_id in ids]
        return [entry for entry in entries if entry is not None]

    async def count(self, tag: str) -> int:
        return int(await self._redis.zcard(self._key("t", tag)))

    async def mark_used(self, entry_id: int) -> Entry | None:
        """Убрать из списка группы, но оставить в архиве ``used``."""
        entry = await self.get(entry_id)
        if entry is None:
            return None
        entry.used = True
        await self._redis.set(self._key("e", entry_id), entry.to_json())
        await self._redis.zrem(self._key("t", entry.tag), str(entry_id))
        await self._redis.zadd(self._key("used"), {str(entry_id): time.time()})
        return entry

    async def delete(self, entry_id: int) -> bool:
        entry = await self.get(entry_id)
        if entry is None:
            return False
        await self._redis.delete(self._key("e", entry_id))
        await self._redis.zrem(self._key("t", entry.tag), str(entry_id))
        await self._redis.zrem(self._key("used"), str(entry_id))
        return True
