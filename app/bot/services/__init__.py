from aiogram import Bot
from loguru import logger
from telethon import TelegramClient

from config import API_HASH, API_ID

from .context import I18nContext, _get_context_obj
from .kafka.router import router as kafka_router
from .keyboards import _get_keyboards_obj, _Keyboards
from .none_module import _NoneModule
from .redis import _get_redis_obj
from .telegram_updater import TelegramUpdater

# i18n context is loaded eagerly — locales are always present in source
context: I18nContext = _get_context_obj()


class _KeyboardsRegistry:
    """Stable handle for the keyboards registry.

    Handlers import this object once; ``init_services`` populates it in place
    so the imported reference stays valid (rebinding the name would not
    propagate to modules that already did ``from services import keyboards``).
    """

    def __init__(self) -> None:
        self._data: dict | None = None

    def _load(self, data: dict) -> None:
        self._data = data

    def _ensure(self) -> dict:
        if self._data is None:
            raise RuntimeError("keyboards accessed before init_services()")
        return self._data

    def __getitem__(self, name):
        return self._ensure()[name]

    def __getattr__(self, name):
        return getattr(self._ensure(), name)


# remaining services are lazy (depend on runtime config / connections)
redis = _NoneModule("redis", "REDIS_URL")
telegram_updater: TelegramUpdater | None = None
keyboards = _KeyboardsRegistry()
telethon_client: TelegramClient | None = None
# kafka_router is imported from .kafka.router as a singleton


def _get_telethon_client_obj() -> TelegramClient:
    return TelegramClient("anon", API_ID, API_HASH, system_version="4.16.30-vxCUSTOM")


def init_services(bot: Bot):
    """Централизованная инициализация сервисов"""
    global redis, telegram_updater, telethon_client

    redis = _get_redis_obj()
    telegram_updater = TelegramUpdater(bot)
    keyboards._load(_get_keyboards_obj())
    telethon_client = _get_telethon_client_obj()

    logger.debug("Services initialized")
