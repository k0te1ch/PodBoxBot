"""Сервисные сообщения: админ пишет текст боту, бот отправляет его в чат.

Начать можно командой ``/service`` или кнопкой «Сервисное сообщение» в
админ-панели. Шаги и подтверждение ведёт DialogEngine
(:mod:`forms.service_message`), сюда приходит готовый текст и расписание:
«сейчас» уходит в чат сразу, остальное ставится в планировщик
(:mod:`services.scheduled_messages`). ``/scheduled`` показывает очередь.
"""

import os
import uuid

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dialog_engine.integrations.aiogram import DialogActiveFilter, DialogCallbackFilter
from loguru import logger
from sagenza_tgbot_sdk.menus import MenuContext

from config import FORWARD_CHAT_USERNAME
from filters.dispatcher_filters import IsAdmin, IsPrivate
from forms.service_message import DIALOG_ID, TEXT, WHEN, service_message_runner
from services import scheduled_messages
from services.i18n import t
from services.metrics import bot_metrics
from utils import chat_card

runner = service_message_runner
storage = runner.storage

SCHEDULED_PREFIX = "sched:"

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)
router.callback_query.filter(IsAdmin)


async def _sender(bot: Bot, chat_id: int) -> chat_card.CardSender:
    """Шаги диалога называют чат по имени и показывают его карточкой."""
    return chat_card.CardSender(bot, chat_id, await chat_card.resolve(bot, FORWARD_CHAT_USERNAME))


async def start_dialog(state: FSMContext, bot: Bot, chat_id: int, language: str) -> None:
    sender = await _sender(bot, chat_id)
    await runner.start(state, sender, context={"lang": language, "chat": sender.card.html})


async def open_from_menu(ctx: MenuContext) -> None:
    """Кнопка админ-панели: запускает тот же диалог, что и ``/service``."""
    await ctx.answer()
    await start_dialog(ctx.data["state"], ctx.data["bot"], ctx.message.chat.id, ctx.locale)


async def send_to_chat(bot: Bot, text: str, language: str, chat: str | None = None) -> str:
    """Отправляет текст в чат форварда; возвращает ответ для админа.

    *chat*: как назвать чат в ответе (HTML); по умолчанию значение из настроек.
    """
    try:
        await bot.send_message(chat_id=FORWARD_CHAT_USERNAME, text=text)
    except Exception as e:
        logger.error(f"service message to {FORWARD_CHAT_USERNAME} failed: {e!r}")
        return t("service_failed", language)
    logger.info(f"service message sent to {FORWARD_CHAT_USERNAME}")
    bot_metrics.admin_action("service_message")
    return t("service_sent", language, chat=chat or FORWARD_CHAT_USERNAME)


def schedule_message(text: str, encoded: str, language: str, chat: str) -> str:
    """Ставит повторное или отложенное сообщение в планировщик; возвращает ответ для админа."""
    schedule = scheduled_messages.parse_schedule(encoded)
    if schedule is None:
        return t("invalid_service_when", language)
    scheduled_messages.add_job(text, schedule, uuid.uuid4().hex[:8])
    bot_metrics.admin_action("service_message_scheduled")
    return t("service_scheduled", language, chat=chat, when=schedule.human(language))


def _scheduled_view(language: str) -> tuple[str, InlineKeyboardMarkup | None]:
    jobs = scheduled_messages.list_jobs()
    if not jobs:
        return t("scheduled_empty", language), None
    lines, rows = [t("scheduled_title", language)], []
    for number, job in enumerate(jobs, 1):
        run_at = scheduled_messages.next_run(job)
        when = run_at.strftime("%d.%m %H:%M") if run_at else "-"
        next_run = t("scheduled_next", language, when=when)
        lines.append(f"{number}. {job.name}\n   {next_run}")
        rows.append([InlineKeyboardButton(text=f"🗑 {number}", callback_data=f"{SCHEDULED_PREFIX}{job.id}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text, Command("scheduled"))
async def scheduled_command(msg: Message, language: str):
    text, markup = _scheduled_view(language)
    await msg.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith(SCHEDULED_PREFIX))
async def scheduled_remove(callback: CallbackQuery, language: str):
    removed = scheduled_messages.remove_job(callback.data.removeprefix(SCHEDULED_PREFIX))
    await callback.answer(t("scheduled_removed" if removed else "scheduled_missing", language))
    text, markup = _scheduled_view(language)
    await callback.message.edit_text(text, reply_markup=markup)


@router.message(F.text, Command("service"))
async def service_command(msg: Message, state: FSMContext, bot: Bot, language: str):
    await start_dialog(state, bot, msg.chat.id, language)


@router.message(F.text, DialogActiveFilter(storage))
async def on_text(msg: Message, state: FSMContext, bot: Bot):
    await runner.on_text(msg.text, state, await _sender(bot, msg.chat.id))


@router.callback_query(DialogCallbackFilter(DIALOG_ID))
async def on_button(callback: CallbackQuery, state: FSMContext, bot: Bot, language: str):
    sender = await _sender(bot, callback.message.chat.id)
    turn = await runner.on_callback(callback.data, state, sender)
    await callback.answer(text=turn.alert, show_alert=bool(turn.alert))
    if turn.finished:
        card = sender.card
        text, when = turn.answers[TEXT], turn.answers.get(WHEN, "now")
        if when == "now":
            result = await send_to_chat(bot, text, language, card.html)
        else:
            result = schedule_message(text, when, language, card.html)
        await callback.message.edit_text(result, link_preview_options=card.preview)
    elif turn.cancelled and not turn.expired:
        await callback.message.edit_text(t("canceled", language))
