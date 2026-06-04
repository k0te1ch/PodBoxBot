import asyncio
import os

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.__meta__ import __version__ as aiogram_version
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.dispatcher.event.telegram import TelegramEventObserver
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import ClientSession
from aiohttp.hdrs import USER_AGENT
from aiohttp.http import SERVER_SOFTWARE
from loguru import logger

from handlers import ROUTERS
from middlewares.base.user_context_middleware import UserContextMiddleware
from services import init_services, redis
from services.none_module import _NoneModule
from utils.bot_methods import get_version, send_release_note
from utils.error_reporting import register_error_handler

# IMPORT SETTINGS
MAIN_MODULE_NAME = os.path.basename(__file__)[:-3]

from config import API_TOKEN, DEBUG, PARSE_MODE
from shared.kafka.consumer import KafkaConsumer

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

        TG_SERVER = TrustEnvAiohttpSession(api=TelegramAPIServer.from_base("http://localhost:8081"))
        logger.opt(colors=True).info(
            f"Telegram bot configured for work with custom server <light-blue>({TG_SERVER.api.base[: TG_SERVER.api.base.find('/bot')]})</light-blue>"
        )
    elif TG_SERVER is not None:
        from aiogram.client.telegram import TelegramAPIServer

        TG_SERVER = TrustEnvAiohttpSession(api=TelegramAPIServer.from_base(TG_SERVER))
        logger.opt(colors=True).info(
            f"Telegram bot configured for work with custom server <light-blue>({TG_SERVER.api.base[: TG_SERVER.api.base.find('/bot')]})</light-blue>"
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
    # Версия запускаемого бота. logger.info выпустит строку только при
    # уровне INFO и ниже — при WARNING+ она молча подавляется (как просили).
    try:
        running_version = await get_version()
    except Exception as e:
        running_version = None
        logger.debug(f"could not read bot version: {e!r}")
    logger.info(f"PodBoxBot v{running_version or '?'} (aiogram {aiogram_version})")

    # Запускаем стартап задачи параллельно с поллингом.
    # send_release_note и kafka-консьюмеры независимы — изолируем падения
    # одного, чтобы не утащить за собой другое. До этого фикса любая
    # ошибка в send_release_note (например, отсутствующий CHANGELOG.md)
    # ловилась внешним @logger.catch, но дальше по функции kafka-консьюмеры
    # уже не регистрировались, и бот тихо работал без приёма result-событий.
    if not DEBUG:
        try:
            await send_release_note()
        except Exception as e:
            logger.warning(f"send_release_note failed (continuing): {e!r}")

    from services import kafka_router
    from services.kafka.handlers import upload_event  # noqa: F401 — регистрирует хендлеры

    # Каждый result-топик слушается в отдельной supervised-задаче. Сам
    # consumer.start() уже дожидается готовности Kafka/Schema Registry, но
    # readiness-ожидание может истечь по таймауту и поднять исключение, а сам
    # poll-loop теоретически может завершиться. Супервайзер ловит любой выход
    # и перезапускает consumer — так бот не остаётся «полуживым» (Telegram
    # отвечает, а приём result-событий молча мёртв) после ребута хоста.
    result_topics = [
        ("publisher.ftp.result", "publisher.ftp.result.group"),
        ("publisher.wordpress.result", "publisher.wordpress.result.group"),
        ("publisher.boosty.result", "publisher.boosty.result.group"),
    ]
    for topic, group_id in result_topics:
        consumer = KafkaConsumer(
            kafka_server="kafka:9092",
            schema_registry_url="http://schema-registry:8081",
            topic=topic,
            group_id=group_id,
        )
        _task = asyncio.create_task(_supervise_consumer(consumer, kafka_router.route))  # noqa: RUF006


async def _supervise_consumer(consumer: "KafkaConsumer", handler, restart_delay: float = 5.0) -> None:
    """Перезапускает consumer-loop при любом выходе/падении.

    consumer.start() в норме блокирует навсегда; вернуться/упасть он может
    только если зависимости не поднялись (readiness-таймаут) или poll-loop
    словил фатальную ошибку. В этом случае ждём и поднимаем заново — бот
    самовосстанавливается без вмешательства.
    """
    while True:
        try:
            await consumer.start(handler)
            logger.warning(f"[supervisor] consumer for {consumer.topic} exited; restarting in {restart_delay:.0f}s")
        except Exception as e:
            logger.exception(f"[supervisor] consumer for {consumer.topic} crashed: {e!r}; restarting in {restart_delay:.0f}s")
        await asyncio.sleep(restart_delay)


@logger.catch
async def on_shutdown():
    pass


def _add_middlewares_to_observers(observers: list[TelegramEventObserver], middlewares: list[BaseMiddleware]) -> None:
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
    _add_middlewares_to_observers([dp.message, dp.callback_query], [UserContextMiddleware()])
    register_error_handler(dp)
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
