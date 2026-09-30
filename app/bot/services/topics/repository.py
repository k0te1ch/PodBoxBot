"""Где лежит очередь тем.

Хендлеры и меню работают только с протоколом :class:`TopicRepository`.
Сейчас его реализует :class:`RedisTopicRepository`; когда в sagenza-tgbot-sdk
появится модуль ``suggest``, рядом встанет адаптер к нему с тем же
протоколом, и переключение сведётся к одной строке в :mod:`.runtime`.

Раскладка ключей Redis для пространства ``ns``:

* ``ns:seq`` — счётчик id;
* ``ns:t:<id>`` — тема в JSON;
* ``ns:s:<status>`` — sorted set тем в этом статусе (score — время создания);
* ``ns:src:<chat>:<message>`` — метка, что сообщение уже стало темой.
"""

import time
from typing import Any, Protocol

from services.topics.models import Topic, TopicStatus

DEFAULT_LIST_LIMIT = 200
# Метка сообщения нужна против повторной доставки апдейта, дольше месяца её
# держать незачем.
ORIGIN_TTL_SECONDS = 30 * 24 * 3600


class TopicRepository(Protocol):
    async def add(self, topic: Topic) -> Topic | None:
        """Сохранить тему и выдать ей id; ``None``, если это сообщение уже сохранено."""

    async def get(self, topic_id: int) -> Topic | None: ...

    async def list(self, status: TopicStatus, limit: int = DEFAULT_LIST_LIMIT) -> list[Topic]:
        """Темы в статусе, свежие сверху."""

    async def count(self, status: TopicStatus) -> int: ...

    async def set_status(self, topic_id: int, status: TopicStatus) -> Topic | None:
        """Перевести тему в статус; ``None``, если темы нет."""


class RedisTopicRepository:
    def __init__(self, redis: Any, namespace: str = "topics") -> None:
        self._redis = redis
        self.namespace = namespace

    def _key(self, *parts: object) -> str:
        return ":".join((self.namespace, *map(str, parts)))

    async def add(self, topic: Topic) -> Topic | None:
        if topic.origin is not None:
            fresh = await self._redis.set(self._key("src", *topic.origin), 1, nx=True, ex=ORIGIN_TTL_SECONDS)
            if not fresh:
                return None
        topic.id = int(await self._redis.incr(self._key("seq")))
        await self._redis.set(self._key("t", topic.id), topic.to_json())
        await self._redis.zadd(self._key("s", topic.status), {str(topic.id): topic.created_at})
        return topic

    async def get(self, topic_id: int) -> Topic | None:
        raw = await self._redis.get(self._key("t", topic_id))
        return Topic.from_json(raw) if raw else None

    async def list(self, status: TopicStatus, limit: int = DEFAULT_LIST_LIMIT) -> list[Topic]:
        ids = await self._redis.zrevrange(self._key("s", status), 0, limit - 1)
        topics = [await self.get(int(topic_id)) for topic_id in ids]
        return [topic for topic in topics if topic is not None]

    async def count(self, status: TopicStatus) -> int:
        return int(await self._redis.zcard(self._key("s", status)))

    async def set_status(self, topic_id: int, status: TopicStatus) -> Topic | None:
        topic = await self.get(topic_id)
        if topic is None:
            return None
        if topic.status != status:
            await self._redis.zrem(self._key("s", topic.status), str(topic_id))
            await self._redis.zadd(self._key("s", status), {str(topic_id): topic.created_at})
            topic.status = status
            topic.updated_at = time.time()
            await self._redis.set(self._key("t", topic_id), topic.to_json())
        return topic
