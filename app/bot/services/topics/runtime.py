"""Сборка очереди тем под этот бот: Redis, настройки, метрики.

Очередь: :class:`SuggestionBox` из модуля ``suggest`` SDK, но без
``SuggestModule``: диалог в личке у бота свой (анкета на DialogEngine, общая
с вариантом C), а разбирают темы ведущие в ``/admin``. Поэтому у очереди нет
модераторов (и карточки SDK никому не уходят) и нет статусов для
уведомлений (автору пишет :mod:`.delivery`: в личку, а если нельзя,
эфемерно в чат). Лимит и длина берутся из ``TOPICS_*``, а не из
``SAGENZA_SUGGEST_*``, чтобы настройка была одна.

Настройки читаются из :mod:`config` при каждом вызове, а не при импорте:
так флаги видны в тестах и после правки конфига.
"""

from typing import Any

from aiogram import Bot
from aiogram.types import Chat, Message, User
from sagenza_tgbot_sdk.i18n import Texts
from sagenza_tgbot_sdk.suggest import RedisSuggestStore, SuggestionBox, SuggestLimits
from sagenza_tgbot_sdk.suggest.texts import DEFAULT_TEXTS

import config as bot_config
from services import redis
from services.i18n import DEFAULT_LOCALE, translator
from services.topics.models import Author
from services.topics.polls import PollStore
from services.topics.repository import SuggestTopicRepository
from services.topics.service import TopicService

QUEUE_PREFIX = "topics:queue"
RATE_PERIOD_SECONDS = 24 * 3600


def topics_enabled(*_args: Any) -> bool:
    """Флаг всей фичи; годится и как фильтр aiogram."""
    return bool(bot_config.TOPICS_ENABLED)


def suggest_texts() -> Texts:
    """Тексты SDK с подменой из ``locales/*.ftl`` бота (``suggest-*``)."""
    return Texts(DEFAULT_TEXTS, translator, DEFAULT_LOCALE)


def suggestion_box(bot: Bot | None = None, metrics: Any = None) -> SuggestionBox:
    """Очередь тем. С *metrics* SDK сам считает ``suggestion_submitted`` и
    ``suggestion_moderated``; *bot* нужен только затем, чтобы SDK не ругался
    в лог, что показать тему некому."""
    box = SuggestionBox(
        RedisSuggestStore(redis, prefix=QUEUE_PREFIX),
        limits=SuggestLimits(
            max_length=bot_config.TOPICS_MAX_LENGTH,
            rate_limit=bot_config.TOPICS_DAILY_LIMIT,
            rate_period=RATE_PERIOD_SECONDS,
        ),
        texts=suggest_texts(),
        notify_statuses=(),
    )
    if bot is not None:
        box.bind(bot, metrics)
    return box


def topic_service(bot: Bot | None = None, metrics: Any = None) -> TopicService:
    return TopicService(
        SuggestTopicRepository(suggestion_box(bot, metrics), redis),
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
