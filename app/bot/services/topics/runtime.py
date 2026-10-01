"""Сборка очереди тем под этот бот: Redis, настройки, метрики.

Настройки читаются из :mod:`config` при каждом вызове, а не при импорте:
так флаги видны в тестах и после правки конфига.
"""

from typing import Any

from aiogram.types import Chat, Message, User

import config as bot_config
from services import redis
from services.topics.models import Author
from services.topics.polls import PollStore
from services.topics.quota import DailyQuota
from services.topics.repository import RedisTopicRepository
from services.topics.service import TopicService


def topics_enabled(*_args: Any) -> bool:
    """Флаг всей фичи; годится и как фильтр aiogram."""
    return bool(bot_config.TOPICS_ENABLED)


def topic_service() -> TopicService:
    return TopicService(
        RedisTopicRepository(redis),
        DailyQuota(redis, bot_config.TOPICS_DAILY_LIMIT, bot_config.TIMEZONE),
        bot_config.TOPICS_MIN_LENGTH,
        bot_config.TOPICS_MAX_LENGTH,
    )


def poll_store() -> PollStore:
    return PollStore(redis)


def count_event(metrics: Any, name: str, **labels: str) -> None:
    """Бизнес-событие в метрики SDK, если модуль метрик подключён."""
    if metrics is not None:
        metrics.event(name, **labels)


def is_topics_chat(chat: Chat) -> bool:
    """Чат тем задан как ``@username`` или числовым id."""
    target = str(bot_config.TOPICS_CHAT).strip()
    if target.startswith("@"):
        return chat.username is not None and chat.username.lower() == target[1:].lower()
    return str(chat.id) == target


def message_link(chat: Chat, message_id: int) -> str | None:
    if chat.username:
        return f"https://t.me/{chat.username}/{message_id}"
    raw = str(chat.id)
    if raw.startswith("-100"):
        return f"https://t.me/c/{raw[4:]}/{message_id}"
    return None


def author_from_user(user: User) -> Author:
    name = f"@{user.username}" if user.username else user.full_name
    language = user.language_code if user.language_code in bot_config.LANGUAGES else "ru"
    return Author(name=name, user_id=user.id, language=language)


def author_of(message: Message) -> Author:
    """Автор сообщения; от имени канала или анонимного админа — без id."""
    if message.sender_chat is not None or message.from_user is None:
        title = message.sender_chat.title if message.sender_chat else message.chat.title
        return Author(name=title or "?")
    return author_from_user(message.from_user)
