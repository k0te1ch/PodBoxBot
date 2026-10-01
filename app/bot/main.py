import asyncio
import functools
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
from sagenza_tgbot_sdk import SdkSettings, setup_sdk
from sagenza_tgbot_sdk.health import HealthModule
from sagenza_tgbot_sdk.host_watch import HostWatchModule, HostWatchSettings
from sagenza_tgbot_sdk.logs import LoggingModule, LoggingSettings
from sagenza_tgbot_sdk.metrics import MetricsModule
from sagenza_tgbot_sdk.notify import NotifyModule
from sagenza_tgbot_sdk.status import StatusModule

from handlers import ROUTERS, bot_menus
from handlers.topics_polls_handler import watch_polls
from middlewares.base.admin_activity_middleware import AdminActivityMiddleware
from middlewares.base.user_context_middleware import UserContextMiddleware
from services import init_services, redis
from services.kafka.handlers.upload_event import record_publish_metrics
from services.metrics import bot_metrics
from services.none_module import _NoneModule
from services.rss import RssWatcher
from services.topics.runtime import topics_enabled
from utils.error_reporting import register_error_handler
from utils.release_notes import get_version, send_release_note

MAIN_MODULE_NAME = os.path.basename(__file__)[:-3]

from config import (
    ADMINS_ID,
    API_TOKEN,
    DEBUG,
    DISK_ALERT_PERCENT,
    DISK_CHECK_INTERVAL,
    KAFKA_SERVER,
    PARSE_MODE,
    RSS_FAILURE_ALERT,
    RSS_FEED_URL,
    RSS_POLL_INTERVAL,
    SCHEMA_REGISTRY_URL,
)
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


def _get_bot_obj() -> Bot:
    from config import LOCAL, TG_SERVER

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
    bot_metrics.set_version(running_version)

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
    # Третье поле: площадка в метриках публикаций (топик её однозначно задаёт).
    result_topics = [
        ("publisher.ftp.result", "publisher.ftp.result.group", "ftp"),
        ("publisher.wordpress.result", "publisher.wordpress.result.group", "wp"),
        ("publisher.boosty.result", "publisher.boosty.result.group", "boosty"),
        ("publisher.vk.result", "publisher.vk.result.group", "vk"),
        ("publisher.patreon.result", "publisher.patreon.result.group", "patreon"),
        ("publisher.sponsr.result", "publisher.sponsr.result.group", "sponsr"),
    ]
    for topic, group_id, platform in result_topics:
        consumer = KafkaConsumer(
            kafka_server=KAFKA_SERVER,
            schema_registry_url=SCHEMA_REGISTRY_URL,
            topic=topic,
            group_id=group_id,
        )
        handler = functools.partial(_route_result, kafka_router.route, platform)
        _task = asyncio.create_task(_supervise_consumer(consumer, handler))  # noqa: RUF006


async def _route_result(route, platform: str, event: dict) -> None:
    """Считает итог публикации в метриках и передаёт событие роутеру."""
    await record_publish_metrics(event, platform)
    await route(event)


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
            bot_metrics.consumer_restarted(consumer.topic)
        except Exception as e:
            logger.exception(
                f"[supervisor] consumer for {consumer.topic} crashed: {e!r}; restarting in {restart_delay:.0f}s"
            )
            bot_metrics.consumer_restarted(consumer.topic)
        await asyncio.sleep(restart_delay)


async def start_rss_watcher(bot: Bot) -> None:
    """Запускает слежение за RSS, если задан адрес ленты и есть Redis."""
    if not RSS_FEED_URL:
        return
    if isinstance(redis, _NoneModule):
        logger.warning("RSS_FEED_URL is set but Redis is not configured: RSS watcher disabled")
        return
    watcher = RssWatcher(bot, redis, RSS_FEED_URL, ADMINS_ID, RSS_POLL_INTERVAL, RSS_FAILURE_ALERT)
    _rss_tasks.add(asyncio.create_task(watcher.run()))


_rss_tasks: set[asyncio.Task] = set()


async def start_topic_polls_watcher(bot: Bot) -> None:
    """Закрывает опросы по темам, у которых вышло время: Telegram о таком
    закрытии боту не сообщает. Нужен Redis, как и всей очереди тем."""
    if not topics_enabled() or isinstance(redis, _NoneModule):
        return
    _topic_poll_tasks.add(asyncio.create_task(watch_polls(bot, bot_metrics.sdk)))


_topic_poll_tasks: set[asyncio.Task] = set()


def _add_middlewares_to_observers(observers: list[TelegramEventObserver], middlewares: list[BaseMiddleware]) -> None:
    for observer in observers:
        for middleware in middlewares:
            observer.middleware(middleware)


def _setup_sdk(dp: Dispatcher) -> None:
    # Синки loguru настраивает config.py, поэтому logging из SDK ставится с
    # configure=False: только контекст апдейта в логах и предупреждение о
    # медленных апдейтах. Ошибки остаются на своём обработчике
    # (utils/error_reporting.py): он шлёт разработчику полный трейсбек без
    # токена бота, а errors из SDK шлёт всем админам только текст исключения.
    settings = SdkSettings(bot_token=API_TOKEN, admin_ids=frozenset(ADMINS_ID))
    host_watch = HostWatchSettings(threshold_percent=DISK_ALERT_PERCENT, interval_seconds=DISK_CHECK_INTERVAL)
    modules = [
        LoggingModule(LoggingSettings(configure=False)),
        # Реестр бота с бизнес-метриками и метриками процесса (services/metrics.py).
        MetricsModule(metrics=bot_metrics.sdk),
        HealthModule(),
        StatusModule(),
        HostWatchModule(host_watch),
        bot_menus,
    ]
    # notify без получателя падает на старте: без ADMINS_ID его просто не ставим.
    if ADMINS_ID:
        modules.append(NotifyModule())
    setup_sdk(dp, settings, modules=modules)


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
        [dp.message, dp.callback_query], [UserContextMiddleware(), AdminActivityMiddleware(ADMINS_ID)]
    )
    bot_metrics.use_redis(None if isinstance(redis, _NoneModule) else redis)
    bot_metrics.set_admins(len(ADMINS_ID))
    register_error_handler(dp)
    _setup_sdk(dp)
    dp.include_routers(*ROUTERS)

    dp.startup.register(on_startup)
    dp.startup.register(start_rss_watcher)
    dp.startup.register(start_topic_polls_watcher)

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
