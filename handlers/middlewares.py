from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

from config import LANGUAGES

# TODO add message to callbacks


class GeneralMiddleware(BaseMiddleware):
    async def get_language(self, user):
        if user.language_code in LANGUAGES:
            return user.language_code

        return "ru"

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        handler_args = data["handler"].params

        if "language" in handler_args:
            data["language"] = await self.get_language(event.from_user)

        if "username" in handler_args:
            data["username"] = event.from_user.username

        return await handler(event, data)


class ChatActionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        long_operation_type = get_flag(data, "long_operation")

        if not long_operation_type:
            return await handler(event, data)

        async with ChatActionSender(action=long_operation_type, chat_id=event.chat.id):
            return await handler(event, data)
