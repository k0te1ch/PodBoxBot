from typing import Awaitable, Callable, Optional
from aiogram.fsm.context import FSMContext
import pytest
from aiogram_tests import MockedRequester
from aiogram_tests.handler import MessageHandler, CallbackQueryHandler
from aiogram_tests.types.dataset import MESSAGE
from app.filters.middlewares import GeneralMiddleware


@pytest.fixture
def handler_factory() -> Callable[..., MessageHandler]:
    """Фикстура для создания обработчика с заданным состоянием и типом обработчика"""

    def _create_handler(
        handler_func,
        command: Optional[str] = None,
        state: Optional[str] = None,
        state_data: Optional[dict] = None,
        dp_middlewares: list = [GeneralMiddleware()],
    ) -> MessageHandler:
        if command:
            return MessageHandler(handler_func, command, dp_middlewares=dp_middlewares, state=state, state_data=state_data)
        return MessageHandler(handler_func, dp_middlewares=dp_middlewares, state=state, state_data=state_data)

    return _create_handler


@pytest.fixture
def callback_handler_factory() -> Callable[..., CallbackQueryHandler]:
    """Фикстура для создания обработчика с заданным состоянием и типом обработчика"""

    def _create_handler(
        handler_func,
        state: Optional[str] = None,
        state_data: Optional[dict] = None,
        dp_middlewares: list = [GeneralMiddleware()],
    ) -> CallbackQueryHandler:
        return CallbackQueryHandler(handler_func, dp_middlewares=dp_middlewares, state=state, state_data=state_data)

    return _create_handler


@pytest.fixture
def bot_factory() -> Callable[[MessageHandler | CallbackQueryHandler], Awaitable[MockedRequester]]:
    """Фикстура для создания MockedRequester с заданным обработчиком"""

    async def _create_bot(handler: MessageHandler|CallbackQueryHandler) -> MockedRequester:
        return MockedRequester(handler)

    return _create_bot


@pytest.fixture
def state_context_factory() -> Callable[..., Awaitable[FSMContext]]:
    """Фикстура для создания контекста состояния FSM с заданным обработчиком"""

    async def _create_state_context(handler: MessageHandler| CallbackQueryHandler, message: Optional[dict] = MESSAGE) -> FSMContext:
        return handler.dp.fsm.get_context(handler.bot, message.chat.id, message.from_user.id)

    return _create_state_context
