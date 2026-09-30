"""Приём и разбор тем: проверки, лимит, смена статуса.

Сервис ничего не знает про Telegram и тексты: причину отказа он возвращает
значением :class:`Refusal`, а что ответить автору, решает хендлер.
"""

from dataclasses import dataclass
from enum import StrEnum

from services.topics.models import Topic, TopicStatus
from services.topics.quota import DailyQuota
from services.topics.repository import TopicRepository


class Refusal(StrEnum):
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    LIMIT = "limit"
    DUPLICATE = "duplicate"


@dataclass
class Suggestion:
    topic: Topic | None = None
    refusal: Refusal | None = None


@dataclass
class StatusChange:
    topic: Topic
    previous: TopicStatus

    @property
    def changed(self) -> bool:
        return self.topic.status != self.previous


class TopicService:
    def __init__(self, repository: TopicRepository, quota: DailyQuota, min_length: int, max_length: int) -> None:
        self.repository = repository
        self.quota = quota
        self.min_length = min_length
        self.max_length = max_length

    def check_text(self, text: str) -> Refusal | None:
        length = len(text.strip())
        if length < self.min_length:
            return Refusal.TOO_SHORT
        if length > self.max_length:
            return Refusal.TOO_LONG
        return None

    async def suggest(self, topic: Topic) -> Suggestion:
        topic.text = " ".join(topic.text.split())
        refusal = self.check_text(topic.text)
        if refusal is not None:
            return Suggestion(refusal=refusal)
        user_id = topic.author.user_id
        if user_id is not None and not await self.quota.take(user_id):
            return Suggestion(refusal=Refusal.LIMIT)
        saved = await self.repository.add(topic)
        if saved is None:
            if user_id is not None:
                await self.quota.give_back(user_id)
            return Suggestion(refusal=Refusal.DUPLICATE)
        return Suggestion(topic=saved)

    async def set_status(self, topic_id: int, status: TopicStatus) -> StatusChange | None:
        topic = await self.repository.get(topic_id)
        if topic is None:
            return None
        previous = topic.status
        updated = await self.repository.set_status(topic_id, status)
        return StatusChange(updated, previous) if updated is not None else None
