from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import config
from services.topics import runtime


class FakeRedis:
    """Команды Redis, которые нужны очереди тем, лимиту и голосованиям, — в памяти."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.ttl: dict[str, int] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return None
        self.values[key] = str(value)
        if ex is not None:
            self.ttl[key] = ex
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        return int(self.values.pop(key, None) is not None)

    async def incr(self, key):
        self.values[key] = str(int(self.values.get(key, 0)) + 1)
        return int(self.values[key])

    async def decr(self, key):
        self.values[key] = str(int(self.values.get(key, 0)) - 1)
        return int(self.values[key])

    async def expire(self, key, seconds):
        self.ttl[key] = seconds
        return True

    async def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(mapping)

    async def zrem(self, key, member):
        self.zsets.get(key, {}).pop(member, None)

    async def zcard(self, key):
        return len(self.zsets.get(key, {}))

    async def zrevrange(self, key, start, end):
        members = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1], reverse=True)
        return [m for m, _ in members[start : end + 1]]

    async def zrangebyscore(self, key, low, high):
        members = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1])
        return [m for m, score in members if low <= score <= high]


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    from handlers import collector_handler

    fake = FakeRedis()
    monkeypatch.setattr(runtime, "redis", fake)
    # Обход меню в тестах открывает и заметки ведущих, им тоже нужен Redis.
    monkeypatch.setattr(collector_handler, "redis", fake)
    return fake


@pytest.fixture(autouse=True)
def topics_on(monkeypatch):
    """Фича включена, чат тем — @test_group, лимит 2 темы в сутки."""
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
