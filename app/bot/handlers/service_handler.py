"""Сервисные сообщения: админ пишет текст боту, бот отправляет его в чат.

Начать можно командой ``/service`` или кнопкой «Сервисное сообщение» в
админ-панели. Шаги и подтверждение ведёт DialogEngine
(:mod:`forms.service_message`), сюда приходит только готовый текст.
"""

import os

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dialog_engine.integrations.aiogram import DefaultSender, DialogActiveFilter, DialogCallbackFilter
from loguru import logger
from sagenza_tgbot_sdk.menus import MenuContext

from config import FORWARD_CHAT_USERNAME
from filters.dispatcher_filters import IsAdmin, IsPrivate
from forms.service_message import DIALOG_ID, TEXT, service_message_runner
from services.i18n import t

runner = service_message_runner
storage = runner.storage

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)
router.callback_query.filter(IsAdmin)


async def start_dialog(state: FSMContext, bot: Bot, chat_id: int, language: str) -> None:
    await runner.start(state, DefaultSender(bot, chat_id), context={"lang": language})


async def open_from_menu(ctx: MenuContext) -> None:
    """Кнопка админ-панели: запускает тот же диалог, что и ``/service``."""
    await ctx.answer()
    await start_dialog(ctx.data["state"], ctx.data["bot"], ctx.message.chat.id, ctx.locale)


async def send_to_chat(bot: Bot, text: str, language: str) -> str:
    """Отправляет текст в чат форварда; возвращает ответ для админа."""
    try:
        await bot.send_message(chat_id=FORWARD_CHAT_USERNAME, text=text)
    except Exception as e:
        logger.error(f"service message to {FORWARD_CHAT_USERNAME} failed: {e!r}")
        return t("service_failed", language)
    logger.info(f"service message sent to {FORWARD_CHAT_USERNAME}")
    return t("service_sent", language, chat=FORWARD_CHAT_USERNAME)


@router.message(F.text, Command("service"))
async def service_command(msg: Message, state: FSMContext, bot: Bot, language: str):
    await start_dialog(state, bot, msg.chat.id, language)


@router.message(F.text, DialogActiveFilter(storage))
async def on_text(msg: Message, state: FSMContext, bot: Bot):
    await runner.on_text(msg.text, state, DefaultSender(bot, msg.chat.id))


@router.callback_query(DialogCallbackFilter(DIALOG_ID))
async def on_button(callback: CallbackQuery, state: FSMContext, bot: Bot, language: str):
    turn = await runner.on_callback(callback.data, state, DefaultSender(bot, callback.message.chat.id))
    await callback.answer(text=turn.alert, show_alert=bool(turn.alert))
    if turn.finished:
        await callback.message.edit_text(await send_to_chat(bot, turn.answers[TEXT], language))
    elif turn.cancelled and not turn.expired:
        await callback.message.edit_text(t("canceled", language))
