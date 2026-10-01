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
в личке.
"""

import os
from collections import Counter
from collections.abc import Awaitable
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)
from loguru import logger
from sagenza_tgbot_sdk.menus import Button, Menu, MenuContext, Submenu

from handlers.topics_form_handler import form_enabled, post_suggest_button, start_private_form
from services.i18n import t
from services.metrics import bot_metrics
from services.topics import Item, Kind
from services.topics.listing import MAX_PAGE_CHARS, Page, item_line, list_pages, parse_numbers, parse_removal
from services.topics.runtime import (
    count_event,
    is_admin,
    is_hosts_chat,
    language_of,
    report_list_size,
    topic_list,
    topics_enabled,
    view_store,
)
from services.topics.views import ListView

TOPICS_MENU = "topics"
LIST_COMMANDS = ("topics", "список")
REMOVE_COMMANDS = ("done", "удали", "del")

MARK = "m"
REMOVE = "d"
REFRESH = "r"
UNDO = "u"
ADD_TOPIC = "at"
ADD_QUESTION = "aq"
AUTHORS = "b"
BAN = "bb"
UNBAN = "bu"

ADD_KINDS = {ADD_TOPIC: Kind.TOPIC, ADD_QUESTION: Kind.QUESTION}
NUMBERS_PER_ROW = 6
MARKED_PREFIX = "✅ "
MAX_AUTHOR_BUTTONS = 50
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


class ListCallback(CallbackData, prefix="tl"):
    a: str
    v: str = ""
    """Метка показанного списка или удаления, которое можно вернуть."""
    n: int = 0
    """Номер пункта или id автора."""


def _is_private(message: Message | None) -> bool:
    return message is not None and message.chat.type == ChatType.PRIVATE


def _hosts_place(event: Message | CallbackQuery) -> bool:
    """Админ в личке бота или в чате ведущих."""
    message = event.message if isinstance(event, CallbackQuery) else event
    if not isinstance(message, Message) or not is_admin(event):
        return False
    return _is_private(message) or is_hosts_chat(message.chat)


def _removal(message: Message) -> dict[str, list[int]] | bool:
    numbers = parse_removal(message.text)
    return {"numbers": numbers} if numbers else False


def _numbers_text(numbers: list[int]) -> str:
    return ", ".join(map(str, numbers))


async def _edit(edit: Awaitable[Any]) -> None:
    """Правка сообщения; «ничего не изменилось» от Telegram не ошибка."""
    try:
        await edit
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


# --- показ списка -----------------------------------------------------------


def _number_button(view: ListView, number: int) -> InlineKeyboardButton:
    label = f"{MARKED_PREFIX}{number}" if number in view.marked else str(number)
    return InlineKeyboardButton(text=label, callback_data=ListCallback(a=MARK, v=view.token, n=number).pack())


def _control(key: str, action: str, locale: str, token: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=t(key, locale), callback_data=ListCallback(a=action, v=token).pack())


def page_markup(view: ListView, page: Page, locale: str, *, last: bool, private: bool) -> InlineKeyboardMarkup | None:
    """Кнопки под сообщением списка: номера его пунктов, а под последним ещё
    и действия со списком."""
    numbers = [_number_button(view, number) for number in page.numbers]
    rows = [numbers[i : i + NUMBERS_PER_ROW] for i in range(0, len(numbers), NUMBERS_PER_ROW)]
    if last:
        refresh = _control("topics_refresh", REFRESH, locale)
        rows.append([_control("topics_remove_marked", REMOVE, locale, view.token), refresh] if view.ids else [refresh])
        if private:
            rows.append(
                [
                    _control("topics_add_topic", ADD_TOPIC, locale),
                    _control("topics_add_question", ADD_QUESTION, locale),
                ]
            )
            rows.append([_control("topics_authors", AUTHORS, locale)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def remark(markup: InlineKeyboardMarkup, view: ListView) -> InlineKeyboardMarkup:
    """Та же клавиатура с отметками из *view* на кнопках номеров."""

    def relabel(button: InlineKeyboardButton) -> InlineKeyboardButton:
        data = button.callback_data or ""
        if not data.startswith(f"{ListCallback.__prefix__}:{MARK}:"):
            return button
        return _number_button(view, ListCallback.unpack(data).n)

    return InlineKeyboardMarkup(
        inline_keyboard=[[relabel(button) for button in row] for row in markup.inline_keyboard]
    )


async def send_list(bot: Bot, chat_id: int, locale: str, *, private: bool) -> ListView:
    """Показать список и запомнить его: номера следующей команды «удали» — отсюда."""
    items = await topic_list().repository.items()
    view = await view_store().remember(chat_id, [item.id for item in items])
    pages = list_pages(items, locale)
    for index, page in enumerate(pages):
        markup = page_markup(view, page, locale, last=index == len(pages) - 1, private=private)
        await bot.send_message(chat_id=chat_id, text=page.text, reply_markup=markup, link_preview_options=NO_PREVIEW)
    report_list_size(items)
    return view


# --- удаление и возврат -----------------------------------------------------


def _lines(title: str, numbered: list[tuple[int, Item]], locale: str) -> str:
    """Заголовок и строки пунктов; длинный хвост сворачивается в «и ещё N»."""
    lines = [title]
    for index, (number, item) in enumerate(numbered):
        line = item_line(number, item, locale)
        if sum(map(len, lines)) + len(line) > MAX_PAGE_CHARS:
            lines.append(t("topics_removed_more", locale, count=len(numbered) - index))
            break
        lines.append(line)
    return "\n".join(lines)


async def remove_numbers(
    bot: Bot, chat_id: int, user_id: int, numbers: list[int], locale: str, *, private: bool, metrics: Any
) -> None:
    """Удалить пункты по номерам последнего показанного списка и показать остаток."""
    views = view_store()
    view = await views.last(chat_id)
    if view is None:
        await bot.send_message(chat_id=chat_id, text=t("topics_view_missing", locale))
        await send_list(bot, chat_id, locale, private=private)
        return
    unknown = [number for number in numbers if view.item_id(number) is None]
    if unknown:
        text = t("topics_numbers_unknown", locale, numbers=_numbers_text(unknown), total=len(view.ids))
        await bot.send_message(chat_id=chat_id, text=text)
        return
    by_id = {view.item_id(number): number for number in numbers}
    removed = await topic_list(bot).remove(list(by_id), moderator_id=user_id)
    gone = sorted(set(numbers) - {by_id[item.id] for item in removed})
    for item in removed:
        count_event(metrics, "topic_removed", kind=item.kind.value)
    logger.info(f"topics: removed {[item.id for item in removed]} by {user_id}, already gone: {gone}")
    if not removed:
        await bot.send_message(chat_id=chat_id, text=t("topics_removed_nothing", locale, numbers=_numbers_text(gone)))
    else:
        text = _lines(t("topics_removed", locale), [(by_id[item.id], item) for item in removed], locale)
        if gone:
            text += "\n" + t("topics_removed_gone", locale, numbers=_numbers_text(gone))
        undo = await views.keep_removed([item.id for item in removed])
        markup = InlineKeyboardMarkup(inline_keyboard=[[_control("topics_undo", UNDO, locale, undo)]])
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, link_preview_options=NO_PREVIEW)
    await send_list(bot, chat_id, locale, private=private)


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
    await message.edit_text(_lines(t("topics_restored", locale), numbered, locale), link_preview_options=NO_PREVIEW)
    await send_list(callback.bot, message.chat.id, locale, private=_is_private(message))


# --- авторы и бан -----------------------------------------------------------


async def authors_view(locale: str) -> tuple[str, InlineKeyboardMarkup | None]:
    """Авторы пунктов списка и бан-лист: кнопка на автора."""
    repository = topic_list().repository
    counts: Counter[int] = Counter()
    names: dict[int, str] = {}
    for item in await repository.items():
        if item.author.user_id is not None:
            counts[item.author.user_id] += 1
            names[item.author.user_id] = item.author.name
    banned = await repository.banned()
    rows = [
        [
            InlineKeyboardButton(
                text=t("topics_author_banned", locale, name=name),
                callback_data=ListCallback(a=UNBAN, n=user_id).pack(),
            )
        ]
        for user_id, name in banned.items()
    ]
    rows += [
        [
            InlineKeyboardButton(
                text=t("topics_author", locale, name=names[user_id], count=count),
                callback_data=ListCallback(a=BAN, n=user_id).pack(),
            )
        ]
        for user_id, count in counts.most_common()
        if user_id not in banned
    ]
    if not rows:
        return t("topics_authors_empty", locale), None
    return t("topics_authors_title", locale), InlineKeyboardMarkup(inline_keyboard=rows[:MAX_AUTHOR_BUTTONS])


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


# --- хендлеры ---------------------------------------------------------------

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])


@router.message(topics_enabled, _hosts_place, Command(*LIST_COMMANDS, ignore_case=True))
async def show_list(msg: Message, bot: Bot):
    bot_metrics.admin_action("topics_list")
    await send_list(bot, msg.chat.id, language_of(msg.from_user), private=_is_private(msg))


@router.message(topics_enabled, _hosts_place, Command(*REMOVE_COMMANDS, ignore_case=True))
async def remove_command(msg: Message, command: CommandObject, bot: Bot, metrics: Any = None):
    locale = language_of(msg.from_user)
    numbers = parse_numbers(command.args)
    if not numbers:
        await msg.answer(t("topics_remove_usage", locale))
        return
    await remove_numbers(
        bot, msg.chat.id, msg.from_user.id, numbers, locale, private=_is_private(msg), metrics=metrics
    )


@router.message(topics_enabled, _hosts_place, F.text, _removal)
async def remove_text(msg: Message, numbers: list[int], bot: Bot, metrics: Any = None):
    """«удали 1, 3, 4» обычным сообщением."""
    locale = language_of(msg.from_user)
    await remove_numbers(
        bot, msg.chat.id, msg.from_user.id, numbers, locale, private=_is_private(msg), metrics=metrics
    )


async def _stale(callback: CallbackQuery, locale: str) -> None:
    """Кнопка от списка, после которого бот показал другой."""
    message = callback.message
    await callback.answer(t("topics_list_stale", locale), show_alert=True)
    await send_list(callback.bot, message.chat.id, locale, private=_is_private(message))


async def _mark(callback: CallbackQuery, data: ListCallback, locale: str) -> None:
    message = callback.message
    view = await view_store().toggle(message.chat.id, data.v, data.n)
    if view is None:
        await _stale(callback, locale)
        return
    marked = _numbers_text(view.marked)
    await callback.answer(t("topics_marked", locale, numbers=marked) if marked else t("topics_marked_none", locale))
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
        private=_is_private(message),
        metrics=metrics,
    )


@router.callback_query(topics_enabled, ListCallback.filter(), _hosts_place)
async def on_list_button(
    callback: CallbackQuery, callback_data: ListCallback, state: FSMContext, bot: Bot, metrics: Any = None
):
    message = callback.message
    locale = language_of(callback.from_user)
    action = callback_data.a
    if action == MARK:
        await _mark(callback, callback_data, locale)
    elif action == REMOVE:
        await _remove_marked(callback, callback_data, locale, metrics)
    elif action == UNDO:
        await _undo(callback, callback_data.v, locale, metrics)
    elif action == REFRESH:
        await callback.answer()
        await send_list(bot, message.chat.id, locale, private=_is_private(message))
    elif not _is_private(message):
        # Добавление и бан только в личке: в чате ведущих анкете негде идти.
        await callback.answer()
    elif action in ADD_KINDS:
        await callback.answer()
        await start_private_form(
            bot, state, message.chat.id, callback.from_user, ADD_KINDS[action], trusted=True, metrics=metrics
        )
    elif action == AUTHORS:
        await callback.answer()
        text, markup = await authors_view(locale)
        await message.answer(text, reply_markup=markup)
    elif action in (BAN, UNBAN):
        await _toggle_ban(callback, action, callback_data.n, locale, metrics)
    else:
        await callback.answer()


@router.callback_query(ListCallback.filter())
async def on_foreign_button(callback: CallbackQuery):
    """Кнопку списка нажал не админ, или темы уже выключены."""
    await callback.answer(t("topics_denied", language_of(callback.from_user)), show_alert=True)


# --- раздел /admin ----------------------------------------------------------


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
