"""Список тем и вопросов для ведущих: показать, почистить, вернуть.

Список один, статусов у пунктов нет::

    Список тем и вопросов:
    1) ВОПРОС - Почему небо голубое?
    2) ТЕМА - Как съездили в отпуск

* Показать: ``/topics`` (``/список``) или ``/admin`` → «Темы и вопросы».
* Удалить обсуждённое: «удали 1, 3, 4», «удали пункты 2-5», ``/done 1 3 4``
  или кнопки с номерами под списком и «Удалить отмеченные». Бот отвечает,
  что удалил, даёт кнопку «Вернуть» и сразу показывает остаток.
* Номера относятся к списку, который бот показал в этом чате последним
  (:mod:`services.topics.views`): пункты, добавленные позже, номера не
  сдвигают. Кнопки под старым списком отвечают, что он устарел.
* «➕ Тема» и «➕ Вопрос»: админ добавляет пункт сам (анкета из
  :mod:`handlers.topics_form_handler`, без лимитов).
* «🚷 Авторы»: бан и разбан авторов пунктов.

Всё это доступно админам в личке бота. Если задан ``TOPICS_HOSTS_CHAT``, в
чате ведущих тоже можно смотреть и чистить список; добавление и бан остаются
в личке. Сами сообщения и кнопки собирает :mod:`handlers.topics_list_view`.
"""

import os
from collections.abc import Awaitable
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger
from sagenza_tgbot_sdk.menus import Button, Menu, MenuContext, Submenu

from handlers.topics_form_handler import form_enabled, post_suggest_button, start_private_form
from handlers.topics_list_view import (
    ADD_QUESTION,
    ADD_TOPIC,
    AUTHORS,
    BAN,
    MARK,
    NO_PREVIEW,
    REFRESH,
    REMOVE,
    UNBAN,
    UNDO,
    ListCallback,
    authors_view,
    is_private,
    marked_text,
    numbered_lines,
    remark,
    remove_numbers,
    send_list,
)
from services.i18n import t
from services.metrics import bot_metrics
from services.topics import Kind
from services.topics.listing import parse_numbers, parse_removal
from services.topics.runtime import (
    count_event,
    is_admin,
    is_hosts_chat,
    language_of,
    topic_list,
    topics_enabled,
    view_store,
)

TOPICS_MENU = "topics"
LIST_COMMANDS = ("topics", "список")
REMOVE_COMMANDS = ("done", "удали", "del")
ADD_KINDS = {ADD_TOPIC: Kind.TOPIC, ADD_QUESTION: Kind.QUESTION}


def _hosts_place(event: Message | CallbackQuery) -> bool:
    """Админ в личке бота или в чате ведущих.

    У нажатия под старым сообщением (Telegram отдаёт такие без содержимого)
    чат всё равно известен: админ получит ответ, что список устарел.
    """
    message = event.message if isinstance(event, CallbackQuery) else event
    if message is None or not is_admin(event):
        return False
    return is_private(message) or is_hosts_chat(message.chat)


def _removal(message: Message) -> dict[str, list[int]] | bool:
    numbers = parse_removal(message.text)
    return {"numbers": numbers} if numbers else False


async def _edit(edit: Awaitable[Any]) -> None:
    """Правка сообщения; «ничего не изменилось» от Telegram не ошибка."""
    try:
        await edit
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


router = Router(name=os.path.splitext(os.path.basename(__file__))[0])


@router.message(topics_enabled, _hosts_place, Command(*LIST_COMMANDS, ignore_case=True))
async def show_list(msg: Message, bot: Bot):
    bot_metrics.admin_action("topics_list")
    await send_list(bot, msg.chat.id, language_of(msg.from_user), private=is_private(msg))


@router.message(topics_enabled, _hosts_place, Command(*REMOVE_COMMANDS, ignore_case=True))
async def remove_command(msg: Message, command: CommandObject, bot: Bot, metrics: Any = None):
    locale = language_of(msg.from_user)
    numbers = parse_numbers(command.args)
    if not numbers:
        await msg.answer(t("topics_remove_usage", locale))
        return
    await remove_numbers(bot, msg.chat.id, msg.from_user.id, numbers, locale, private=is_private(msg), metrics=metrics)


@router.message(topics_enabled, _hosts_place, F.text, _removal)
async def remove_text(msg: Message, numbers: list[int], bot: Bot, metrics: Any = None):
    """«удали 1, 3, 4» обычным сообщением."""
    locale = language_of(msg.from_user)
    await remove_numbers(bot, msg.chat.id, msg.from_user.id, numbers, locale, private=is_private(msg), metrics=metrics)


async def _stale(callback: CallbackQuery, locale: str) -> None:
    """Кнопка от списка, после которого бот показал другой."""
    message = callback.message
    await callback.answer(t("topics_list_stale", locale), show_alert=True)
    await send_list(callback.bot, message.chat.id, locale, private=is_private(message))


async def _mark(callback: CallbackQuery, data: ListCallback, locale: str) -> None:
    message = callback.message
    view = await view_store().toggle(message.chat.id, data.v, data.n)
    if view is None:
        await _stale(callback, locale)
        return
    await callback.answer(marked_text(view, locale))
    await _edit(message.edit_reply_markup(reply_markup=remark(message.reply_markup, view)))


async def _remove_marked(callback: CallbackQuery, data: ListCallback, locale: str, metrics: Any) -> None:
    message = callback.message
    view = await view_store().current(message.chat.id, data.v)
    if view is None:
        await _stale(callback, locale)
        return
    if not view.marked:
        await callback.answer(t("topics_mark_first", locale), show_alert=True)
        return
    await callback.answer()
    await remove_numbers(
        callback.bot,
        message.chat.id,
        callback.from_user.id,
        view.marked,
        locale,
        private=is_private(message),
        metrics=metrics,
    )


async def _undo(callback: CallbackQuery, token: str, locale: str, metrics: Any) -> None:
    message = callback.message
    item_ids = await view_store().take_removed(token)
    if item_ids is None:
        await callback.answer(t("topics_undo_expired", locale), show_alert=True)
        await _edit(message.edit_reply_markup(reply_markup=None))
        return
    restored = await topic_list(callback.bot).restore(item_ids)
    for item in restored:
        count_event(metrics, "topic_restored", kind=item.kind.value)
    logger.info(f"topics: restored {[item.id for item in restored]} by {callback.from_user.id}")
    await callback.answer()
    positions = {item.id: number for number, item in enumerate(await topic_list().repository.items(), start=1)}
    numbered = sorted((positions.get(item.id, 0), item) for item in restored)
    text = numbered_lines(t("topics_restored", locale), numbered, locale)
    await _edit(message.edit_text(text, link_preview_options=NO_PREVIEW))
    await send_list(callback.bot, message.chat.id, locale, private=is_private(message))


async def _author_name(user_id: int) -> str:
    items = await topic_list().repository.items()
    return next((item.author.name for item in items if item.author.user_id == user_id), str(user_id))


async def _toggle_ban(callback: CallbackQuery, action: str, user_id: int, locale: str, metrics: Any) -> None:
    repository = topic_list().repository
    if action == BAN:
        await repository.ban(user_id, await _author_name(user_id))
    else:
        await repository.unban(user_id)
    name = "ban" if action == BAN else "unban"
    logger.info(f"topics: {name} of author {user_id} by {callback.from_user.id}")
    count_event(metrics, "topic_author", action=name)
    await callback.answer(t(f"topics_{name}_done", locale))
    text, markup = await authors_view(locale)
    await _edit(callback.message.edit_text(text, reply_markup=markup))


async def _private_action(
    callback: CallbackQuery, data: ListCallback, state: FSMContext, locale: str, metrics: Any
) -> None:
    """Добавление и бан: только в личке, в чате ведущих анкете негде идти."""
    message = callback.message
    if not is_private(message):
        await callback.answer()
    elif data.a in ADD_KINDS:
        await callback.answer()
        await start_private_form(
            callback.bot, state, message.chat.id, callback.from_user, ADD_KINDS[data.a], trusted=True, metrics=metrics
        )
    elif data.a == AUTHORS:
        await callback.answer()
        text, markup = await authors_view(locale)
        await message.answer(text, reply_markup=markup)
    elif data.a in (BAN, UNBAN):
        await _toggle_ban(callback, data.a, data.n, locale, metrics)
    else:
        await callback.answer()


@router.callback_query(topics_enabled, ListCallback.filter(), _hosts_place)
async def on_list_button(
    callback: CallbackQuery, callback_data: ListCallback, state: FSMContext, bot: Bot, metrics: Any = None
):
    message = callback.message
    locale = language_of(callback.from_user)
    action = callback_data.a
    if not isinstance(message, Message):
        # Сообщение слишком старое, править его нельзя: проще показать список заново.
        await _stale(callback, locale)
    elif action == MARK:
        await _mark(callback, callback_data, locale)
    elif action == REMOVE:
        await _remove_marked(callback, callback_data, locale, metrics)
    elif action == UNDO:
        await _undo(callback, callback_data.v, locale, metrics)
    elif action == REFRESH:
        await callback.answer()
        await send_list(bot, message.chat.id, locale, private=is_private(message))
    else:
        await _private_action(callback, callback_data, state, locale, metrics)


@router.callback_query(ListCallback.filter())
async def on_foreign_button(callback: CallbackQuery):
    """Кнопку списка нажал не админ, или темы уже выключены."""
    await callback.answer(t("topics_denied", language_of(callback.from_user)), show_alert=True)


async def _show_from_menu(ctx: MenuContext) -> None:
    await ctx.answer()
    await send_list(ctx.data["bot"], ctx.message.chat.id, ctx.locale, private=True)


def _add_from_menu(kind: Kind):
    async def add(ctx: MenuContext) -> None:
        await ctx.answer()
        user = ctx.event.from_user if ctx.event is not None else None
        await start_private_form(
            ctx.data["bot"],
            ctx.data["state"],
            ctx.message.chat.id,
            user,
            kind,
            trusted=True,
            metrics=ctx.data.get("metrics"),
        )

    return add


async def _authors_from_menu(ctx: MenuContext) -> None:
    await ctx.answer()
    text, markup = await authors_view(ctx.locale)
    await ctx.message.answer(text, reply_markup=markup)


def topics_submenu(visible_if) -> Submenu:
    """Пункт админ-панели «Темы и вопросы»: виден админам, когда фича включена."""
    menu = Menu(
        TOPICS_MENU,
        title="topics_panel",
        columns=2,
        items=[
            Button("topics_show", id="show", handler=_show_from_menu, row=True),
            Button("topics_add_topic", id="add_topic", handler=_add_from_menu(Kind.TOPIC)),
            Button("topics_add_question", id="add_question", handler=_add_from_menu(Kind.QUESTION)),
            Button("topics_authors", id="authors", handler=_authors_from_menu, row=True),
            Button(
                "topics_post_button",
                id="post_button",
                handler=post_suggest_button,
                confirm=True,
                row=True,
                visible_if=form_enabled,
            ),
        ],
    )
    return Submenu("admin_topics", menu, id="topics", visible_if=lambda ctx: topics_enabled() and visible_if(ctx))
