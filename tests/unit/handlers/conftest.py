from collections.abc import Awaitable, Callable

import pytest
from aiogram.fsm.context import FSMContext
from aiogram_tests import MockedRequester
from aiogram_tests.handler import CallbackQueryHandler, MessageHandler
from aiogram_tests.types.dataset import MESSAGE

from middlewares.base.general_middleware import GeneralMiddleware

# aiogram-testing registers ``dp_middlewares`` on every dispatcher observer,
# including the root ``update`` observer whose event is an ``Update``. The bot's
# message/callback middlewares (e.g. GeneralMiddleware) expect a ``Message`` /
# ``CallbackQuery`` and read ``event.from_user``. Keep them off the ``update``
# observer so they only run where the event type matches, mirroring how the bot
# registers them at runtime.
_EXCLUDE_OBSERVERS = ["update"]


@pytest.fixture(autouse=True, scope="session")
def _init_keyboards():
    """Populate the keyboards registry.

    At runtime ``init_services(bot)`` loads the keyboards; the unit tests never
    call it, so handlers that read ``keyboards["..."]`` would raise. The
    keyboards themselves don't need a bot, so load them directly here.
    """
    from services import keyboards
    from services.keyboards import _get_keyboards_obj

    keyboards._load(_get_keyboards_obj())
    yield


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
                exclude_observer_methods=_EXCLUDE_OBSERVERS,
                state=state,
                state_data=state_data,
            )
        return MessageHandler(
            handler_func,
            dp_middlewares=dp_middlewares,
            exclude_observer_methods=_EXCLUDE_OBSERVERS,
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
            exclude_observer_methods=_EXCLUDE_OBSERVERS,
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
