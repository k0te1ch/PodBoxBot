"""Голосования по темам: какой опрос из каких тем собран и чем кончился.

Раскладка ключей Redis для пространства ``ns``:

* ``ns:seq`` — счётчик id;
* ``ns:p:<id>`` — голосование в JSON;
* ``ns:tg:<poll_id>`` — id голосования по id опроса Telegram;
* ``ns:all`` — sorted set всех голосований (score — время создания);
* ``ns:closed:<id>`` — метка, что итог уже подведён: закрытие приходит и
  ответом ``stopPoll``, и апдейтом ``poll``, а подводить итог нужно один раз.
"""

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TopicPoll:
    topic_ids: list[int]
    options: list[str]
    chat_id: int
    message_id: int
    poll_id: str
    id: int = 0
    votes: list[int] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    closed_at: float | None = None
    winner_id: int | None = None

    @property
    def closed(self) -> bool:
        return self.closed_at is not None

    @property
    def total_votes(self) -> int:
        return sum(self.votes)

    def leader(self) -> int | None:
        """Индекс варианта с наибольшим числом голосов; при равенстве — первый
        по порядку, без голосов — ``None``."""
        if not self.votes or max(self.votes) == 0:
            return None
        return self.votes.index(max(self.votes))

    def is_tie(self) -> bool:
        return bool(self.votes) and max(self.votes) > 0 and self.votes.count(max(self.votes)) > 1

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "TopicPoll":
        return cls(**json.loads(raw))


class PollStore:
    def __init__(self, redis: Any, namespace: str = "topics:poll") -> None:
        self._redis = redis
        self.namespace = namespace

    def _key(self, *parts: object) -> str:
        return ":".join((self.namespace, *map(str, parts)))

    async def add(self, poll: TopicPoll) -> TopicPoll:
        poll.id = int(await self._redis.incr(self._key("seq")))
        await self.save(poll)
        await self._redis.set(self._key("tg", poll.poll_id), poll.id)
        await self._redis.zadd(self._key("all"), {str(poll.id): poll.created_at})
        return poll

    async def save(self, poll: TopicPoll) -> None:
        await self._redis.set(self._key("p", poll.id), poll.to_json())

    async def get(self, poll_id: int) -> TopicPoll | None:
        raw = await self._redis.get(self._key("p", poll_id))
        return TopicPoll.from_json(raw) if raw else None

    async def by_telegram_id(self, telegram_poll_id: str) -> TopicPoll | None:
        poll_id = await self._redis.get(self._key("tg", telegram_poll_id))
        return await self.get(int(poll_id)) if poll_id else None

    async def list(self, limit: int = 20) -> list[TopicPoll]:
        """Голосования, свежие сверху."""
        ids = await self._redis.zrevrange(self._key("all"), 0, limit - 1)
        polls = [await self.get(int(poll_id)) for poll_id in ids]
        return [poll for poll in polls if poll is not None]

    async def claim_close(self, poll_id: int) -> bool:
        """``True`` только первому, кто подводит итог голосования."""
        return bool(await self._redis.set(self._key("closed", poll_id), 1, nx=True))
