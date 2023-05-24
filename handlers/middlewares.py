import inspect

from aiogram.dispatcher.handler import current_handler
from aiogram.dispatcher.middlewares import BaseMiddleware

from bot import db, dp
from config import LANGUAGES


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
        await handler(obj, data, *args)


dp.middleware.setup(GeneralMiddleware())
