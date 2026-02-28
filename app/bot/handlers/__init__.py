from aiogram.types import BotCommand

from .admin_handler import router as admin_handler_router
from .audio_handler import router as audio_handler_router
from .bot_handler import router as bot_handler_router
from .ftp_handler import router as ftp_handler_router
from .podcast_handler import router as podcast_handler_router
from .wordpress_handler import router as wordpress_handler_router

ROUTERS = [
    admin_handler_router,
    podcast_handler_router,
    audio_handler_router,
    ftp_handler_router,
    wordpress_handler_router,
    bot_handler_router,
]

COMMANDS = [
    # BotCommand(command="menu", description="Вызов меню"),
    # BotCommand(command="feedback", description="Обратная связь"),
]
