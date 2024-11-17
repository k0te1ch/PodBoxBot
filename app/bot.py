import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from handlers import ROUTERS
from filters.middlewares import GeneralMiddleware
from loguru import logger
from services.none_module import _NoneModule
from services.redis import redis

# TODO: Создать отдельную директорию для middlewares (зачем?)
# TODO: Объекты бота вывести в отдельную директорию и как-то их подгружать (избавимся от bot.py возможно)
# TODO: Автоматом подгружать все handlers (__init__.py)
# TODO: CI/CD
# TODO: pre-commit
# TODO: i386

# IMPORT SETTINGS
MAIN_MODULE_NAME = os.path.basename(__file__)[:-3]

from config import API_TOKEN, PARSE_MODE

logger.debug("Loading settings from config")


# GET TG BOT OBJECT
def _get_bot_obj() -> Bot:
    from config import LOCAL, TG_SERVER

    # TODO CHECK THIS
    if TG_SERVER is None and LOCAL:
        from aiogram.client.session.aiohttp import AiohttpSession
        from aiogram.client.telegram import TelegramAPIServer

        TG_SERVER = AiohttpSession(api=TelegramAPIServer.from_base("http://localhost:8081"))
        logger.opt(colors=True).info(
            f"Telegram bot configured for work with custom server <light-blue>({TG_SERVER.api.base[:TG_SERVER.api.base.find('/bot')]})</light-blue>"
        )
    elif TG_SERVER is not None:
        from aiogram.client.session.aiohttp import AiohttpSession
        from aiogram.client.telegram import TelegramAPIServer

        TG_SERVER = AiohttpSession(api=TelegramAPIServer.from_base(TG_SERVER))
        logger.opt(colors=True).info(
            f"Telegram bot configured for work with custom server <light-blue>({TG_SERVER.api.base[:TG_SERVER.api.base.find('/bot')]})</light-blue>"
        )
    else:
        logger.opt(colors=True).debug("The standard api tg server is used")

    bot = Bot(token=API_TOKEN, session=TG_SERVER, default=DefaultBotProperties(parse_mode=PARSE_MODE))
    logger.debug("Bot is configured")
    return bot


# GET DISPATCHER OBJECT
def _get_dp_obj(bot, redis):
    logger.debug("Dispatcher configurate:")
    if not isinstance(redis, _NoneModule):
        storage = RedisStorage(redis)
        logger.debug("Used by Redis")
    else:
        storage = MemoryStorage()
        logger.debug("Used by MemoryStorage")
    dp = Dispatcher(storage=storage)
    dp.message.middleware(GeneralMiddleware())
    dp.callback_query.middleware(GeneralMiddleware())
    dp.include_routers(*ROUTERS)

    logger.debug("Dispatcher is configured")
    return dp


if __name__ == MAIN_MODULE_NAME:
    bot = _get_bot_obj()
    dp = _get_dp_obj(bot, redis)

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    from cli import cli

    logger.debug("Calling the cli module")

    cli()
