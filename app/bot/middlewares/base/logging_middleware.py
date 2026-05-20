from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from loguru import logger


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware для логирования вызовов handler'ов
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        handler_info = data.get("handler")
        chat = data.get("chat")
        chat_title = None
        if chat.type in ["supergroup", "channel"]:
            chat_title = chat.title
        username = user.username if user else "unknown"
        handler_name = handler_info.callback.__name__ if handler_info else "unknown"

        logger.debug(
            f"[{username}]{f'|[{chat_title}]' if chat_title else ''}:Called {handler_name} ({type(event).__name__})"
        )

        return await handler(event, data)
