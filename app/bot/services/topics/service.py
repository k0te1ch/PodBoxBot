"""Приём и разбор тем: проверки, смена статуса.

Сервис ничего не знает про Telegram и тексты: причину отказа он возвращает
значением :class:`Refusal`, а что ответить автору, решает хендлер. Лимит на
автора и бан-лист проверяет очередь SDK, сервис только переводит её отказ
в :class:`Refusal`.
"""

from dataclasses import dataclass
from enum import StrEnum

from sagenza_tgbot_sdk.suggest import RejectReason, SuggestionRejectedError

from services.topics.models import Topic, TopicStatus
from services.topics.repository import TopicRepository


class Refusal(StrEnum):
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    LIMIT = "limit"
    BANNED = "banned"
    DUPLICATE = "duplicate"


_SDK_REFUSALS = {
    RejectReason.EMPTY: Refusal.TOO_SHORT,
    RejectReason.TOO_LONG: Refusal.TOO_LONG,
    RejectReason.RATE_LIMITED: Refusal.LIMIT,
    RejectReason.BANNED: Refusal.BANNED,
}


@dataclass
class Suggestion:
    topic: Topic | None = None
    refusal: Refusal | None = None


@dataclass
class StatusChange:
    topic: Topic
    previous: TopicStatus
    previous_note: str | None = None

    @property
    def changed(self) -> bool:
        return self.topic.status != self.previous or self.topic.note != self.previous_note


class TopicService:
    def __init__(self, repository: TopicRepository, min_length: int, max_length: int) -> None:
        self.repository = repository
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
        try:
            saved = await self.repository.add(topic)
        except SuggestionRejectedError as error:
            # Ссылку на сообщение бот строит сам, BAD_LINK сюда не доходит.
            return Suggestion(refusal=_SDK_REFUSALS.get(error.reason, Refusal.TOO_SHORT))
        if saved is None:
            return Suggestion(refusal=Refusal.DUPLICATE)
        return Suggestion(topic=saved)

    async def set_status(
        self, topic_id: int, status: TopicStatus, *, note: str | None = None, moderator_id: int | None = None
    ) -> StatusChange | None:
        topic = await self.repository.get(topic_id)
        if topic is None:
            return None
        updated = await self.repository.set_status(topic_id, status, note=note, moderator_id=moderator_id)
        return StatusChange(updated, topic.status, topic.note) if updated is not None else None
