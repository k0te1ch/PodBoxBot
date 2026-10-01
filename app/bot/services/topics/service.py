"""Приём пунктов и чистка списка.

Сервис ничего не знает про Telegram и тексты: причину отказа он возвращает
значением :class:`Refusal`, а что ответить автору, решает хендлер. Лимит на
автора и бан-лист проверяет очередь SDK, сервис только переводит её отказ
в :class:`Refusal`.
"""

from dataclasses import dataclass
from enum import StrEnum

from sagenza_tgbot_sdk.suggest import RejectReason, SuggestionRejectedError

from services.topics.models import Item
from services.topics.repository import ListRepository


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
class Added:
    item: Item | None = None
    refusal: Refusal | None = None


class TopicList:
    def __init__(self, repository: ListRepository, min_length: int, max_length: int) -> None:
        self.repository = repository
        self.min_length = min_length
        self.max_length = max_length

    def check_text(self, text: str, *, trusted: bool = False) -> Refusal | None:
        length = len(text.strip())
        if length < (1 if trusted else self.min_length):
            return Refusal.TOO_SHORT
        if length > self.max_length:
            return Refusal.TOO_LONG
        return None

    async def add(self, item: Item, *, trusted: bool = False) -> Added:
        """Добавить пункт. *trusted*: пункт добавляет админ, ему не мешают
        ни лимит, ни бан-лист, ни минимальная длина."""
        item.text = " ".join(item.text.split())
        refusal = self.check_text(item.text, trusted=trusted)
        if refusal is not None:
            return Added(refusal=refusal)
        try:
            saved = await self.repository.add(item, check_limits=not trusted)
        except SuggestionRejectedError as error:
            # Ссылку на сообщение бот строит сам, BAD_LINK сюда не доходит.
            return Added(refusal=_SDK_REFUSALS.get(error.reason, Refusal.TOO_SHORT))
        if saved is None:
            return Added(refusal=Refusal.DUPLICATE)
        return Added(item=saved)

    async def remove(self, item_ids: list[int], moderator_id: int | None = None) -> list[Item]:
        """Убрать пункты из списка; в ответе только те, что там были."""
        removed = [await self.repository.remove(item_id, moderator_id) for item_id in item_ids]
        return [item for item in removed if item is not None]

    async def restore(self, item_ids: list[int]) -> list[Item]:
        """Вернуть убранные пункты; в ответе только те, что вернулись."""
        restored = [await self.repository.restore(item_id) for item_id in item_ids]
        return [item for item in restored if item is not None]
