import itertools
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fakeredis import FakeAsyncRedis as FakeRedis

import config
from services.topics import runtime


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    """Redis в памяти: очередь тем SDK, голосования и заметки ведущих."""
    from handlers import collector_handler

    fake = FakeRedis(decode_responses=True)
    monkeypatch.setattr(runtime, "redis", fake)
    # Обход меню в тестах открывает и заметки ведущих, им тоже нужен Redis.
    monkeypatch.setattr(collector_handler, "redis", fake)
    return fake


@pytest.fixture(autouse=True)
def ticking_clock(monkeypatch):
    """Часы очереди SDK: каждый вызов на секунду позже, порядок тем без гонок."""
    ticks = itertools.count(1_700_000_000)
    build = runtime.suggestion_box

    def box(*args, **kwargs):
        built = build(*args, **kwargs)
        built.clock = lambda: float(next(ticks))
        return built

    monkeypatch.setattr(runtime, "suggestion_box", box)


@pytest.fixture(autouse=True)
def topics_on(monkeypatch):
    """Фича включена, чат тем @test_group, лимит 2 темы в сутки."""
    monkeypatch.setattr(config, "TOPICS_ENABLED", True)
    monkeypatch.setattr(config, "TOPICS_CHAT", "@test_group")
    monkeypatch.setattr(config, "TOPICS_HASHTAG", "тема")
    monkeypatch.setattr(config, "TOPICS_DAILY_LIMIT", 2)
    monkeypatch.setattr(config, "TOPICS_MIN_LENGTH", 5)
    monkeypatch.setattr(config, "TOPICS_MAX_LENGTH", 50)


@pytest.fixture(autouse=True)
def _admins():
    with patch("filters.dispatcher_filters.ADMINS", ["admin"]):
        yield


@pytest.fixture
def bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _group_message(text: str, *, user_id: int | None = 7, username: str | None = "listener", message_id: int = 100):
    """Сообщение в чате тем от слушателя (или от имени канала, если ``user_id`` нет)."""
    msg = MagicMock()
    msg.text = text
    msg.caption = None
    msg.message_id = message_id
    msg.chat.id = -1001234567890
    msg.chat.username = "test_group"
    msg.chat.title = "Test group"
    msg.react = AsyncMock()
    if user_id is None:
        msg.from_user = None
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
