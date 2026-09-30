"""Тема от слушателя и её статусы.

Статусы те же, что у предложений модуля ``suggest`` из sagenza-tgbot-sdk:
очередь тем хранится в нём (:mod:`.repository`), а хендлеры видят только
:class:`Topic`.
"""

import time
from dataclasses import dataclass, field
from enum import StrEnum

from sagenza_tgbot_sdk.suggest import SuggestionStatus

TopicStatus = SuggestionStatus


class TopicSource(StrEnum):
    HASHTAG = "hashtag"
    FORM = "form"


@dataclass
class Author:
    """Кто предложил тему. ``user_id`` нет у анонимного админа и постов от имени канала."""

    name: str
    user_id: int | None = None
    language: str = "ru"


@dataclass
class Topic:
    text: str
    author: Author
    source: TopicSource
    status: TopicStatus = TopicStatus.NEW
    id: int = 0
    created_at: float = field(default_factory=time.time)
    chat_id: int | None = None
    message_id: int | None = None
    link: str | None = None
    note: str | None = None
    """Номер выпуска, в который взяли тему; его же получает автор."""

    @property
    def origin(self) -> tuple[int, int] | None:
        """Сообщение, из которого тема собрана: по нему отсекаются повторы."""
        if self.chat_id is None or self.message_id is None:
            return None
        return self.chat_id, self.message_id
