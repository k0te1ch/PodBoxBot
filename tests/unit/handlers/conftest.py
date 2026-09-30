from collections.abc import Awaitable, Callable

import pytest
from aiogram.fsm.context import FSMContext
from aiogram_tests import MockedRequester
from aiogram_tests.handler import CallbackQueryHandler, MessageHandler
from aiogram_tests.types.dataset import MESSAGE

from middlewares.base.general_middleware import GeneralMiddleware


@pytest.fixture
def handler_factory() -> Callable[..., MessageHandler]:
    """Фикстура для создания обработчика с заданным состоянием и типом обработчика"""

    def _create_handler(
        handler_func,
        command: str | None = None,
        state: str | None = None,
        state_data: dict | None = None,
        dp_middlewares: list | None = None,
    ) -> MessageHandler:
        if dp_middlewares is None:
            dp_middlewares = [GeneralMiddleware()]
        if command:
            return MessageHandler(
                handler_func,
                command,
                dp_middlewares=dp_middlewares,
                state=state,
                state_data=state_data,
            )
        return MessageHandler(
            handler_func,
            dp_middlewares=dp_middlewares,
            state=state,
            state_data=state_data,
        )

    return _create_handler


@pytest.fixture
def callback_handler_factory() -> Callable[..., CallbackQueryHandler]:
    """Фикстура для создания обработчика с заданным состоянием и типом обработчика"""

    def _create_handler(
        handler_func,
        state: str | None = None,
        state_data: dict | None = None,
        dp_middlewares: list | None = None,
    ) -> CallbackQueryHandler:
        if dp_middlewares is None:
            dp_middlewares = [GeneralMiddleware()]
        return CallbackQueryHandler(
            handler_func,
            dp_middlewares=dp_middlewares,
            state=state,
            state_data=state_data,
        )

    return _create_handler


@pytest.fixture
def bot_factory() -> Callable[[MessageHandler | CallbackQueryHandler], Awaitable[MockedRequester]]:
    """Фикстура для создания MockedRequester с заданным обработчиком"""

    async def _create_bot(
        handler: MessageHandler | CallbackQueryHandler,
    ) -> MockedRequester:
        return MockedRequester(handler)

    return _create_bot


@pytest.fixture
def state_context_factory() -> Callable[..., Awaitable[FSMContext]]:
    """Фикстура для создания контекста состояния FSM с заданным обработчиком"""

    async def _create_state_context(
        handler: MessageHandler | CallbackQueryHandler, message: dict | None = MESSAGE
    ) -> FSMContext:
        return handler.dp.fsm.get_context(handler.bot, message.chat.id, message.from_user.id)

    return _create_state_context


class FakeRedis:
    """Те команды Redis, что нужны EntryStore, — в памяти."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}

    async def set(self, key, value, nx=False):
        if nx and key in self.values:
            return None
        self.values[key] = str(value)
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        return int(self.values.pop(key, None) is not None)

    async def incr(self, key):
        self.values[key] = str(int(self.values.get(key, 0)) + 1)
        return int(self.values[key])

    async def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(mapping)

    async def zrem(self, key, member):
        self.zsets.get(key, {}).pop(member, None)

    async def zcard(self, key):
        return len(self.zsets.get(key, {}))

    async def zrevrange(self, key, start, end):
        members = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1], reverse=True)
        return [m for m, _ in members[start : end + 1]]


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    from handlers import collector_handler

    fake = FakeRedis()
    monkeypatch.setattr(collector_handler, "redis", fake)
    return fake
