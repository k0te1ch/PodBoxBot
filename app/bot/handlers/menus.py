"""Все inline-меню бота на модуле ``menus`` из sagenza-tgbot-sdk.

Кнопка несёт свой хендлер, callback_data и «Назад» генерирует SDK, а при
старте ``Menus.setup`` валит бота, если какая-то кнопка ведёт в никуда.

* Админ-панель (``/admin``): Бот → перезапустить / логи; сервисное сообщение;
  заметки ведущих и вопросы слушателей (:mod:`handlers.collector_handler`).
* Меню аудио висит под готовым MP3: FTP, сайт, пересылка в чат, а у
  послешоу — платные площадки (Boosty, VK Donut, Patreon, Sponsr), каждая
  видна, только когда включена флагом ``<ПЛОЩАДКА>_ENABLED``.
  Основной эпизод и послешоу — разные корни, чтобы «Назад» из FTP вёл
  в своё меню.
"""

import os
from dataclasses import fields
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User
from loguru import logger
from sagenza_tgbot_sdk.menus import Button, Menu, MenuContext, Menus, Submenu

import config as bot_config
from config import LANGUAGES
from filters.dispatcher_filters import IsAdmin, IsPrivate
from handlers.admin_handler import restart, send_logs
from handlers.audio_handler import forward_to_chat
from handlers.boosty_handler import upload_Boosty
from handlers.collector_handler import collection_submenus
from handlers.ftp_handler import upload_FTP
from handlers.paywalled_handler import PATREON, SPONSR, VK, Platform, upload_to
from handlers.service_handler import open_from_menu as open_service_message
from handlers.wordpress_handler import upload_WP
from services.i18n import DEFAULT_LOCALE, translator
from services.metrics import bot_metrics
from utils.menu_context import is_admin

ADMIN_MENU = "admin"
AUDIO_MAIN_MENU = "audio_main"
AUDIO_POST_MENU = "audio_post"

# Заголовок меню аудио — подпись под файлом, она не должна меняться при
# переходах по подменю.
AUDIO_TITLE = "done_mp3"


class _MediaAwareContext(MenuContext):
    """Контекст, который умеет перерисовывать меню под аудио.

    SDK меняет меню через ``edit_text``, а у сообщения с файлом текста нет —
    только подпись. Для таких сообщений правится подпись и клавиатура.
    """

    async def put(self, text: str, markup: InlineKeyboardMarkup | None) -> None:
        message = self.message
        if self.callback is None or message is None or message.text is not None:
            await super().put(text, markup)
            return
        try:
            await message.edit_caption(caption=text, reply_markup=markup)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error):
                raise


class BotMenus(Menus):
    def context(
        self,
        event: CallbackQuery | Message | None,
        data: dict[str, Any] | None = None,
        **extra: Any,
    ) -> MenuContext:
        base = super().context(event, data, **extra)
        return _MediaAwareContext(**{f.name: getattr(base, f.name) for f in fields(base)})


def _locale(user: User | None, data: dict[str, Any]) -> str:
    """Язык как у UserContextMiddleware: из данных хендлера или language_code."""
    language = data.get("language")
    if isinstance(language, str):
        return language
    code = user.language_code if user else None
    return code if code in LANGUAGES else DEFAULT_LOCALE


def _publish_menu(menu_id: str, key: str, handler) -> Menu:
    return Menu(menu_id, title=AUDIO_TITLE, items=[Button(key, id="upload", handler=handler)])


def _platform_visible(flag: str):
    """``visible_if`` для кнопки платной площадки: админ и площадка включена.

    Флаг читается при каждой отрисовке, а не при сборке меню, — так его
    видно в тестах и после правки конфига без пересборки меню.
    """

    def visible(ctx: MenuContext) -> bool:
        return is_admin(ctx) and bool(getattr(bot_config, flag, False))

    return visible


def _platform_submenu(platform: Platform) -> Submenu:
    return Submenu(
        f"audio_{platform.key}",
        _publish_menu(platform.key, f"{platform.key}_upload", upload_to(platform)),
        id=platform.key,
        visible_if=_platform_visible(f"{platform.key.upper()}_ENABLED"),
    )


def build_menus() -> BotMenus:
    bot_menu = Menu(
        "bot",
        title="bot_panel",
        columns=2,
        items=[
            Button("bot_restart", id="restart", handler=restart, confirm=True),
            Button("bot_logs", id="logs", handler=send_logs, row=True),
        ],
    )
    admin_menu = Menu(
        ADMIN_MENU,
        title="admin_panel",
        items=[
            Submenu("admin_bot", bot_menu, id="bot", visible_if=is_admin),
            Button("admin_service", id="service", handler=open_service_message, visible_if=is_admin),
            *collection_submenus(is_admin),
        ],
    )
    audio_main = Menu(
        AUDIO_MAIN_MENU,
        title=AUDIO_TITLE,
        columns=2,
        items=[
            Submenu("audio_ftp", _publish_menu("ftp_main", "ftp_upload", upload_FTP), id="ftp", visible_if=is_admin),
            Submenu("audio_site", _publish_menu("wp", "wp_upload", upload_WP), id="wp", visible_if=is_admin),
            Button(
                "audio_forward",
                id="forward",
                handler=forward_to_chat,
                confirm=True,
                row=True,
                visible_if=is_admin,
            ),
        ],
    )
    audio_post = Menu(
        AUDIO_POST_MENU,
        title=AUDIO_TITLE,
        columns=2,
        items=[
            Submenu("audio_ftp", _publish_menu("ftp_post", "ftp_upload", upload_FTP), id="ftp", visible_if=is_admin),
            Submenu(
                "audio_boosty",
                _publish_menu("boosty", "boosty_upload", upload_Boosty),
                id="boosty",
                visible_if=_platform_visible("BOOSTY_ENABLED"),
            ),
            _platform_submenu(VK),
            _platform_submenu(PATREON),
            _platform_submenu(SPONSR),
        ],
    )
    return BotMenus(admin_menu, audio_main, audio_post, translator=translator, locale_getter=_locale)


menus = build_menus()


async def audio_menu_markup(event: Message | CallbackQuery, type_episode: str) -> InlineKeyboardMarkup:
    """Клавиатура меню аудио для готового эпизода."""
    menu_id = AUDIO_MAIN_MENU if type_episode == "main" else AUDIO_POST_MENU
    _text, markup = await menus.render(menus.context(event), menu_id)
    return markup


router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)


@router.message(F.text, Command("admin"))
async def admin(msg: Message, username: str, language: str):
    """Handle the /admin command"""
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Admin panel called")
    bot_metrics.admin_action("admin_panel")
    await menus.send(msg, ADMIN_MENU, language=language)
