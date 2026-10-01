"""Тема от слушателя и её статусы."""

import json
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum


class TopicStatus(StrEnum):
    NEW = "new"
    LATER = "later"
    TAKEN = "taken"
    REJECTED = "rejected"


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
    updated_at: float | None = None
    chat_id: int | None = None
    message_id: int | None = None
    link: str | None = None

    @property
    def origin(self) -> tuple[int, int] | None:
        """Сообщение, из которого тема собрана: по нему отсекаются повторы."""
        if self.chat_id is None or self.message_id is None:
            return None
        return self.chat_id, self.message_id

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "Topic":
        data = json.loads(raw)
        data["author"] = Author(**data["author"])
        data["source"] = TopicSource(data["source"])
        data["status"] = TopicStatus(data["status"])
        return cls(**data)
