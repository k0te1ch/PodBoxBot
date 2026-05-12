import asyncio
import os
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import ClientSession

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.dispatcher.event.telegram import TelegramEventObserver
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from loguru import logger

from aiohttp.hdrs import USER_AGENT
from aiohttp.http import SERVER_SOFTWARE
from aiogram.__meta__ import __version__ as aiogram_version
from handlers import ROUTERS
from middlewares.base.error_middleware import ErrorMiddleware
from middlewares.base.user_context_middleware import UserContextMiddleware
from services import init_services, redis
from services.none_module import _NoneModule
from utils.bot_methods import send_release_note

# IMPORT SETTINGS
MAIN_MODULE_NAME = os.path.basename(__file__)[:-3]

from shared.kafka.consumer import KafkaConsumer

from config import API_HASH, API_ID, API_TOKEN, DEBUG, PARSE_MODE

logger.debug("Loading settings from config")


class TrustEnvAiohttpSession(AiohttpSession):
    """AiohttpSession that honours HTTP(S)_PROXY env vars via trust_env=True."""

    async def create_session(self) -> ClientSession:
        if self._should_reset_connector:
            await self.close()

        if self._session is None or self._session.closed:
            self._session = ClientSession(
                connector=self._connector_type(**self._connector_init),
                headers={USER_AGENT: f"{SERVER_SOFTWARE} aiogram/{aiogram_version}"},
                trust_env=True,
            )
            self._should_reset_connector = False

        return self._session


# GET TG BOT OBJECT
def _get_bot_obj() -> Bot:
    from config import LOCAL, TG_SERVER

    # TODO CHECK THIS
    if TG_SERVER is None and LOCAL:
        from aiogram.client.telegram import TelegramAPIServer

        TG_SERVER = TrustEnvAiohttpSession(
            api=TelegramAPIServer.from_base("http://localhost:8081")
        )
        logger.opt(colors=True).info(
            f"Telegram bot configured for work with custom server <light-blue>({TG_SERVER.api.base[:TG_SERVER.api.base.find('/bot')]})</light-blue>"
        )
    elif TG_SERVER is not None:
        from aiogram.client.telegram import TelegramAPIServer

        TG_SERVER = TrustEnvAiohttpSession(api=TelegramAPIServer.from_base(TG_SERVER))
        logger.opt(colors=True).info(
            f"Telegram bot configured for work with custom server <light-blue>({TG_SERVER.api.base[:TG_SERVER.api.base.find('/bot')]})</light-blue>"
        )
    else:
        TG_SERVER = TrustEnvAiohttpSession()
        logger.opt(colors=True).debug("The standard api tg server is used")

    bot = Bot(
        token=API_TOKEN,
        session=TG_SERVER,
        default=DefaultBotProperties(parse_mode=PARSE_MODE),
    )
    logger.debug("Bot is configured")
    return bot


@logger.catch
async def on_startup():
    # Запускаем стартап задачи параллельно с поллингом
    if not DEBUG:
        await send_release_note()

    from services import kafka_router
    from services.kafka.handlers import upload_event  # noqa: F401 — регистрирует хендлеры

    # FTP result consumer
    ftp_consumer = KafkaConsumer(
        kafka_server="kafka:9092",
        schema_registry_url="http://schema-registry:8081",
        topic="publisher.ftp.result",
        group_id="publisher.ftp.result.group",
    )
    asyncio.create_task(ftp_consumer.start(kafka_router.route))

    # WordPress result consumer
    wp_consumer = KafkaConsumer(
        kafka_server="kafka:9092",
        schema_registry_url="http://schema-registry:8081",
        topic="publisher.wordpress.result",
        group_id="publisher.wordpress.result.group",
    )
    asyncio.create_task(wp_consumer.start(kafka_router.route))


@logger.catch
async def on_shutdown():
    pass


def _add_middlewares_to_observers(
    observers: list[TelegramEventObserver], middlewares: list[BaseMiddleware]
) -> None:
    for observer in observers:
        for middleware in middlewares:
            observer.middleware(middleware)


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
    _add_middlewares_to_observers(
        [dp.message, dp.callback_query], [ErrorMiddleware(), UserContextMiddleware()]
    )
    dp.include_routers(*ROUTERS)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.debug("Dispatcher is configured")
    return dp


if __name__ == MAIN_MODULE_NAME:
    bot = _get_bot_obj()
    dp = _get_dp_obj(bot, redis)
    init_services(bot)

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    from cli import cli

    logger.debug("Calling the cli module")

    cli()
