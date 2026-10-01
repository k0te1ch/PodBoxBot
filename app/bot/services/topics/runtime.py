"""Сборка списка тем и вопросов под этот бот: Redis, настройки, чаты.

Хранилище: :class:`SuggestionBox` из модуля ``suggest`` SDK, но без
``SuggestModule``: анкета у бота своя (на DialogEngine), а список ведущие
смотрят и чистят командами и кнопками бота. Поэтому у очереди нет модераторов
(карточки SDK никому не уходят), нет уведомлений автору о статусе и нет
метрик SDK: бот считает свои (``topic_added`` с типом и источником). Лимит и
длина берутся из ``TOPICS_*``, а не из ``SAGENZA_SUGGEST_*``, чтобы настройка
была одна.

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
from filters.dispatcher_filters import IsAdmin
from services import redis
from services.i18n import DEFAULT_LOCALE, translator
from services.metrics import bot_metrics
from services.topics.models import Author, Item, Kind
from services.topics.repository import SuggestListRepository
from services.topics.service import TopicList
from services.topics.views import ViewStore

QUEUE_PREFIX = "topics:queue"
RATE_PERIOD_SECONDS = 24 * 3600


def topics_enabled(*_args: Any) -> bool:
    """Флаг всей фичи; годится и как фильтр aiogram."""
    return bool(bot_config.TOPICS_ENABLED)


def suggestion_box(bot: Bot | None = None) -> SuggestionBox:
    """Очередь SDK под списком. *bot* нужен только затем, чтобы SDK не ругался
    в лог, что показать пункт некому."""
    box = SuggestionBox(
        RedisSuggestStore(redis, prefix=QUEUE_PREFIX),
        limits=SuggestLimits(
            max_length=bot_config.TOPICS_MAX_LENGTH,
            rate_limit=bot_config.TOPICS_DAILY_LIMIT,
            rate_period=RATE_PERIOD_SECONDS,
        ),
        texts=Texts(DEFAULT_TEXTS, translator, DEFAULT_LOCALE),
        notify_statuses=(),
    )
    if bot is not None:
        box.bind(bot)
    return box


def topic_list(bot: Bot | None = None) -> TopicList:
    return TopicList(
        SuggestListRepository(suggestion_box(bot), redis),
        bot_config.TOPICS_MIN_LENGTH,
        bot_config.TOPICS_MAX_LENGTH,
    )


def view_store() -> ViewStore:
    return ViewStore(redis)


def count_event(metrics: Any, name: str, **labels: str) -> None:
    """Бизнес-событие в метрики SDK, если модуль метрик подключён."""
    if metrics is not None:
        metrics.event(name, **labels)


def report_list_size(items: list[Item]) -> None:
    """Размер списка по типам в gauge ``podboxbot_topics_list_size``."""
    bot_metrics.topics_list_size({kind.value: sum(item.kind is kind for item in items) for kind in Kind})


async def refresh_list_size() -> None:
    report_list_size(await topic_list().repository.items())


def _is_chat(chat: Chat, target: str | None) -> bool:
    """Чат задан как ``@username`` или числовым id."""
    target = str(target or "").strip()
    if not target:
        return False
    if target.startswith("@"):
        return chat.username is not None and chat.username.lower() == target[1:].lower()
    return str(chat.id) == target


def is_topics_chat(chat: Chat) -> bool:
    return _is_chat(chat, bot_config.TOPICS_CHAT)


def is_hosts_chat(chat: Chat) -> bool:
    """Чат ведущих. Чат тем им быть не может: список увидели бы слушатели."""
    return _is_chat(chat, bot_config.TOPICS_HOSTS_CHAT) and not is_topics_chat(chat)


def is_admin(event: Any) -> bool:
    """Тот же список ADMINS, что у фильтра IsAdmin; событие без автора — не админ."""
    return getattr(event, "from_user", None) is not None and IsAdmin(event)


def kind_of_hashtags(tags: list[str]) -> Kind | None:
    """Тип пункта по хештегам сообщения: чей хештег встретился первым."""
    kinds = dict.fromkeys(bot_config.TOPICS_HASHTAGS, Kind.TOPIC)
    kinds |= dict.fromkeys(bot_config.TOPICS_QUESTION_HASHTAGS, Kind.QUESTION)
    return next((kinds[tag] for tag in tags if tag in kinds), None)


def all_hashtags() -> list[str]:
    return [*bot_config.TOPICS_HASHTAGS, *bot_config.TOPICS_QUESTION_HASHTAGS]


def language_of(user: User | None) -> str:
    code = user.language_code if user is not None else None
    return code if code in bot_config.LANGUAGES else DEFAULT_LOCALE


def author_from_user(user: User) -> Author:
    name = f"@{user.username}" if user.username else user.full_name
    return Author(name=name, user_id=user.id, language=language_of(user))


def author_of(message: Message) -> Author:
    """Автор сообщения.

    Пост от имени канала: автор — канал, с его id, чтобы лимит и бан работали
    и для него. Анонимный админ пишет от имени самой группы: у него id нет.
    """
    sender = message.sender_chat
    if sender is not None:
        user_id = sender.id if sender.id != message.chat.id else None
        return Author(name=sender.title or "?", user_id=user_id)
    if message.from_user is None:
        return Author(name=message.chat.title or "?")
    return author_from_user(message.from_user)
