"""``/start``: приветствие и главное меню. Выпуск сам по себе не заводится.

Админ видит свои разделы (новый выпуск, темы и вопросы, заметки, админка),
остальные: кнопку «Предложить тему или вопрос» и справку. Оформление выпуска
начинается только явным действием: кнопкой «Новый выпуск», командой ``/new``
или присланным mp3 (:mod:`handlers.podcast_handler`).

Ссылку ``?start=topic`` разбирает :mod:`handlers.topics_form_handler`: его
роутер стоит раньше.
"""

import os

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from filters.dispatcher_filters import IsAdmin, IsPrivate
from handlers.menus import HOME_MENU, HOME_USER_MENU, menus
from services.metrics import bot_metrics

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate)


@router.message(F.text, CommandStart())
async def start(msg: Message, language: str):
    """Главное меню: своё для админа и для всех остальных."""
    admin = msg.from_user is not None and IsAdmin(msg)
    bot_metrics.admin_action("home" if admin else "home_user")
    await menus.send(msg, HOME_MENU if admin else HOME_USER_MENU, language=language)
