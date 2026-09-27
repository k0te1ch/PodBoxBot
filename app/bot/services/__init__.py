from aiogram import Bot
from loguru import logger

from .kafka.router import router as kafka_router
from .redis import redis  # eagerly initialized singleton — see note below
from .telegram_updater import TelegramUpdater

# `redis` is re-exported from .redis where it's eagerly built at module
# import time — Redis.from_url() doesn't actually open a socket, so it's
# safe pre-event-loop. We re-export instead of reassigning in
# init_services() because `from services import redis` in other modules
# (utils/release_notes.py, services/scheduler.py, main.py) captures the
# name at *import* time; later reassignment here would not propagate to
# those modules, leaving them stuck with whatever was bound first.

telegram_updater: TelegramUpdater | None = None
# kafka_router is imported from .kafka.router as a singleton


def init_services(bot: Bot):
    """Централизованная инициализация сервисов"""
    global telegram_updater

    telegram_updater = TelegramUpdater(bot)

    logger.debug("Services initialized")
