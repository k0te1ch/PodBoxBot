"""Новый вход в Boosty через бота.

Админ открывает инструкцию командой ``/boosty`` или кнопкой «Обновить вход» под
сообщением о слетевшем входе, копирует сниппетом куки boosty.to и присылает их
боту в личку. Бот сразу удаляет сообщение с куками, пишет файл токенов
публишера и проверяет вход на блоге. Публишер подхватывает новый файл сам.
"""

import asyncio
import os
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from loguru import logger

import config
from filters.dispatcher_filters import IsAdmin
from services.boosty_session import DOWN_KEY, LOGIN_CALLBACK, save_login, verify_login
from services.i18n import t
from services.redis import redis
from services.topics.runtime import language_of
from shared.boosty_cookies import SNIPPET, CookieError, looks_like_cookies

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(F.chat.type == ChatType.PRIVATE, IsAdmin)
router.callback_query.filter(IsAdmin)


def instructions(locale: str) -> str:
    return t("boosty_login_howto", locale, snippet=f"<pre><code>{escape(SNIPPET)}</code></pre>")


@router.message(Command("boosty"))
async def show_instructions(msg: Message):
    await msg.answer(instructions(language_of(msg.from_user)), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == LOGIN_CALLBACK)
async def login_button(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(instructions(language_of(callback.from_user)), parse_mode=ParseMode.HTML)


def _cookies(msg: Message) -> bool:
    return looks_like_cookies(msg.text)


@router.message(F.text, _cookies)
async def receive_cookies(msg: Message):
    locale = language_of(msg.from_user)
    text = msg.text
    try:
        await msg.delete()
    except Exception as e:
        logger.warning(f"boosty login: could not delete the message with cookies: {e!r}")
    try:
        data = await asyncio.to_thread(save_login, text, config.BOOSTY_AUTH_FILE)
    except CookieError as e:
        await msg.answer(t("boosty_login_bad", locale, reason=str(e)))
        return
    except OSError as e:
        logger.error(f"boosty login: cannot write {config.BOOSTY_AUTH_FILE}: {e!r}")
        await msg.answer(t("boosty_login_no_file", locale))
        return
    logger.info(f"boosty login: new token file written by {msg.from_user.id}")
    verified = await verify_login(data, config.BOOSTY_BLOG)
    if verified is False:
        await msg.answer(t("boosty_login_rejected", locale))
        return
    await redis.delete(DOWN_KEY)
    key = "boosty_login_saved" if verified else "boosty_login_saved_unchecked"
    await msg.answer(t(key, locale, blog=config.BOOSTY_BLOG or "-"))
