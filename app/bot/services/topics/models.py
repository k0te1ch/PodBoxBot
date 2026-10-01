"""Пункт списка тем и вопросов: что это, от кого и откуда."""

import time
from dataclasses import dataclass, field
from enum import StrEnum


class Kind(StrEnum):
    TOPIC = "topic"
    QUESTION = "question"


class Source(StrEnum):
    HASHTAG = "hashtag"
    """Сообщение с хештегом в чате."""
    FORM = "form"
    """Анкета или команда слушателя."""
    ADMIN = "admin"
    """Админ добавил пункт сам, в личке бота."""
    REPLY = "reply"
    """Админ добавил чужое сообщение из чата, ответив на него командой."""


@dataclass
class Author:
    """Кто предложил пункт.

    ``user_id``: id человека, а у поста от имени канала — id канала
    (отрицательный): по нему считается лимит и работает бан. У анонимного
    админа группы id нет.
    """

    name: str
    user_id: int | None = None
    language: str = "ru"

    @property
    def is_person(self) -> bool:
        """Человек, которому можно написать: не канал и не аноним."""
        return self.user_id is not None and self.user_id > 0


@dataclass
class Item:
    text: str
    kind: Kind
    author: Author
    source: Source
    id: int = 0
    created_at: float = field(default_factory=time.time)
    chat_id: int | None = None
    message_id: int | None = None

    @property
    def origin(self) -> tuple[int, int] | None:
        """Сообщение, из которого пункт собран: по нему отсекаются повторы."""
        if self.chat_id is None or self.message_id is None:
            return None
        return self.chat_id, self.message_id
