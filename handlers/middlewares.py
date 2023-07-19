import inspect
from datetime import datetime
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery


from aiogram.dispatcher.flags import get_flag
from aiogram.utils.chat_action import ChatActionSender
from aiogram.dispatcher.middlewares import BaseMiddleware

from bot import db, dp
from config import LANGUAGES

"""
class GeneralMiddleware(BaseMiddleware):
    def __init__(self):
        super(GeneralMiddleware, self).__init__()

    async def pre_process(self, msg, data, *args):
        pass

    async def post_process(self, msg, data, *args):
        pass

    async def get_language(self, user):
        if user.language_code in LANGUAGES:
            return user.language_code

        return 'ru'

    async def on_process_message(self, msg, data):
        spec = inspect.getfullargspec(current_handler.get())

        if 'language' in spec.args:  # set language if handler requires it
            data['language'] = await self.get_language(msg.from_user)

    async def on_process_callback_query(self, msg, data):
        spec = inspect.getfullargspec(current_handler.get())

        if 'language' in spec.args:  # set language if handler requires it
            data['language'] = await self.get_language(msg.from_user)

    async def trigger(self, action, args):
        obj, *args, data = args
        if action.startswith('pre_process_'):
            return await self.pre_process(obj, data, *args)
        elif action.startswith('post_process_'):
            return await self.post_process(obj, data, *args)

        handler_name = f"on_{action}"
        handler = getattr(self, handler_name, None)
        if not handler:
            return None
        await handler(obj, data, *args)"""

class GeneralMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        return await handler(event, data)

class ChatActionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        long_operation_type = get_flag(data, "long_operation")

        # Если такого флага на хэндлере нет
        if not long_operation_type:
            return await handler(event, data)

        # Если флаг есть
        async with ChatActionSender(
                action=long_operation_type, 
                chat_id=event.chat.id
        ):
            return await handler(event, data)

dp.middleware.setup(GeneralMiddleware())
