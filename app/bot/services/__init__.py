from aiogram import Bot
from loguru import logger
from telethon import TelegramClient

from config import API_HASH, API_ID

from .context import _get_context_obj
from .kafka.router import KafkaEventRouter
from .keyboards import _get_keyboards_obj, _Keyboards
from .none_module import _NoneModule
from .redis import _get_redis_obj
from .telegram_updater import TelegramUpdater

# глобальные сервисы
redis = _NoneModule("redis", "REDIS_URL")
telegram_updater: TelegramUpdater | None = None
context = _NoneModule("text", "CONTEXT_FILE")
keyboards: _Keyboards | None = None
telethon_client: TelegramClient | None = None
kafka_router: KafkaEventRouter | None = None


def _get_telethon_client_obj() -> TelegramClient:
    return TelegramClient("anon", API_ID, API_HASH, system_version="4.16.30-vxCUSTOM")


def init_services(bot: Bot):
    """Централизованная инициализация сервисов"""
    global redis, telegram_updater, context, keyboards, telethon_client, kafka_router

    redis = _get_redis_obj()
    telegram_updater = TelegramUpdater(bot)
    context = _get_context_obj()
    keyboards = _get_keyboards_obj()
    telethon_client = _get_telethon_client_obj()
    kafka_router = KafkaEventRouter()

    logger.debug("Services initialized")
