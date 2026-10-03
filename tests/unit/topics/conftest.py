import itertools
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.enums import ChatType
from fakeredis import FakeAsyncRedis as FakeRedis

import config
from services.topics import Author, Item, Kind, Source, runtime

GROUP_ID = -1001234567890
CHANNEL_ID = -1005550001111


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    """Redis в памяти: список тем SDK, снимки списка и заметки ведущих."""
    from handlers import collector_handler

    fake = FakeRedis(decode_responses=True)
    monkeypatch.setattr(runtime, "redis", fake)
    # Обход меню в тестах открывает и заметки ведущих, им тоже нужен Redis.
    monkeypatch.setattr(collector_handler, "redis", fake)
    return fake


@pytest.fixture(autouse=True)
def ticking_clock(monkeypatch):
    """Часы очереди SDK: каждый вызов на секунду позже, порядок пунктов без гонок."""
    ticks = itertools.count(1_700_000_000)
    build = runtime.suggestion_box

    def box(*args, **kwargs):
        built = build(*args, **kwargs)
        built.clock = lambda: float(next(ticks))
        return built

    monkeypatch.setattr(runtime, "suggestion_box", box)


@pytest.fixture(autouse=True)
def topics_on(monkeypatch):
    """Фича включена, чат тем @test_group, лимит 2 пункта в сутки."""
    monkeypatch.setattr(config, "TOPICS_ENABLED", True)
    monkeypatch.setattr(config, "TOPICS_CHAT", "@test_group")
    monkeypatch.setattr(config, "TOPICS_HOSTS_CHAT", None)
    monkeypatch.setattr(config, "TOPICS_HASHTAGS", ["тема"])
    monkeypatch.setattr(config, "TOPICS_QUESTION_HASHTAGS", ["вопрос"])
    monkeypatch.setattr(config, "TOPICS_ACK_REACTION", True)
    # Тесты списка смотрят на обычный текст; таблица проверяется отдельно.
    monkeypatch.setattr(config, "RICH_MESSAGES", False)
    monkeypatch.setattr(config, "TOPICS_ACK_EMOJI", ["👍"])
    monkeypatch.setattr(config, "TOPICS_ACK_EPHEMERAL", True)
    monkeypatch.setattr(config, "TOPICS_DAILY_LIMIT", 2)
    monkeypatch.setattr(config, "TOPICS_MIN_LENGTH", 5)
    monkeypatch.setattr(config, "TOPICS_MAX_LENGTH", 50)
    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "ephemeral")


@pytest.fixture(autouse=True)
def _admins():
    with patch("filters.dispatcher_filters.ADMINS", ["admin"]):
        yield


@pytest.fixture
def bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.edit_message_text = AsyncMock()
    return bot


def _group_message(
    text: str,
    *,
    user_id: int | None = 7,
    username: str | None = "listener",
    message_id: int = 100,
    reply_to=None,
    ephemeral_id: int | None = None,
    sender_chat_id: int | None = CHANNEL_ID,
):
    """Сообщение в чате тем от слушателя.

    Без ``user_id`` это пост от имени канала ``sender_chat_id``; с
    ``sender_chat_id=GROUP_ID`` пишет анонимный админ, от имени самой группы.
    Telegram в обоих случаях подставляет в ``from_user`` служебного бота.
    """
    msg = MagicMock()
    msg.text = text
    msg.caption = None
    msg.message_id = message_id
    msg.ephemeral_message_id = ephemeral_id
    msg.chat.id = GROUP_ID
    msg.chat.type = ChatType.SUPERGROUP
    msg.chat.username = "test_group"
    msg.chat.title = "Test group"
    msg.reply_to_message = reply_to
    msg.forum_topic_created = None
    msg.react = AsyncMock()
    msg.reply = AsyncMock()
    msg.delete = AsyncMock()
    if user_id is None:
        msg.from_user.id = 136817688
        msg.from_user.username = "Channel_Bot"
        msg.from_user.language_code = None
        msg.sender_chat.id = sender_chat_id
        msg.sender_chat.title = "Podcast channel"
    else:
        msg.sender_chat = None
        msg.from_user.id = user_id
        msg.from_user.username = username
        msg.from_user.full_name = "Listener"
        msg.from_user.language_code = "ru"
    return msg


@pytest.fixture
def group_message():
    return _group_message


@pytest.fixture
def add_item():
    """Пункт сразу в хранилище, мимо проверок: заготовка списка для теста."""

    async def add(text: str, kind: Kind = Kind.TOPIC, user_id: int | None = 7, name: str = "@listener") -> Item:
        item = Item(text=text, kind=kind, author=Author(name=name, user_id=user_id), source=Source.HASHTAG)
        return await runtime.topic_list().repository.add(item, check_limits=False)

    return add
