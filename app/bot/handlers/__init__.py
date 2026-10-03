from aiogram.types import BotCommand

from .bot_handler import router as bot_handler_router
from .collector_handler import router as collector_handler_router
from .home_handler import router as home_handler_router
from .menus import menus as bot_menus
from .menus import router as menus_router
from .podcast_handler import router as podcast_handler_router
from .rss_handler import router as rss_handler_router
from .service_handler import router as service_handler_router
from .status_handler import router as status_handler_router
from .topics_form_handler import router as topics_form_handler_router
from .topics_handler import router as topics_handler_router
from .topics_list_handler import router as topics_list_handler_router

# Кнопки меню (админка, FTP/сайт/Boosty, пересылка) роутит модуль menus SDK —
# он ставится в main._setup_sdk, здесь только команды и диалог загрузки.
ROUTERS = [
    menus_router,
    status_handler_router,
    collector_handler_router,
    topics_handler_router,
    topics_list_handler_router,
    topics_form_handler_router,
    home_handler_router,
    podcast_handler_router,
    service_handler_router,
    rss_handler_router,
    bot_handler_router,
]

# Меню команд для всех приватных чатов. /admin и /new сюда намеренно не
# попадают: их роутеры закрыты фильтрами IsPrivate+IsAdmin, и светить их всем
# незачем. Обе вещи админ открывает кнопками главного меню.
COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
]
