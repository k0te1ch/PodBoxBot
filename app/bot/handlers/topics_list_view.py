"""Что бот показывает ведущим про список тем и вопросов.

Сообщения списка с кнопками, отчёт об удалении с кнопкой «Вернуть», панель
авторов. Кто и когда это вызывает, решает :mod:`handlers.topics_list_handler`.
"""

from collections import Counter
from typing import Any

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, MaybeInaccessibleMessage
from loguru import logger

from services.i18n import t
from services.topics import Item
from services.topics.listing import MARK as MARKED_PREFIX
from services.topics.listing import MAX_PAGE_CHARS, Page, item_line, list_pages
from services.topics.runtime import count_event, report_list_size, topic_list, view_store
from services.topics.views import ListView

MARK = "m"
REMOVE = "d"
REFRESH = "r"
UNDO = "u"
ADD_TOPIC = "at"
ADD_QUESTION = "aq"
AUTHORS = "b"
BAN = "bb"
UNBAN = "bu"

NUMBERS_PER_ROW = 6
MAX_AUTHOR_BUTTONS = 50
MAX_TOAST_CHARS = 190
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


class ListCallback(CallbackData, prefix="tl"):
    a: str
    v: str = ""
    """Метка показанного списка или удаления, которое можно вернуть."""
    n: int = 0
    """Номер пункта или id автора."""


def is_private(message: MaybeInaccessibleMessage | None) -> bool:
    return message is not None and message.chat.type == ChatType.PRIVATE


def numbers_text(numbers: list[int]) -> str:
    return ", ".join(map(str, numbers))


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


def marked_text(view: ListView, locale: str) -> str:
    """Всплывающий ответ на отметку; он не длиннее 200 символов."""
    if not view.marked:
        return t("topics_marked_none", locale)
    text = t("topics_marked", locale, numbers=numbers_text(view.marked))
    return text if len(text) <= MAX_TOAST_CHARS else t("topics_marked_count", locale, count=len(view.marked))


async def send_list(bot: Bot, chat_id: int, locale: str, *, private: bool) -> ListView:
    """Показать список и запомнить его: номера следующей команды «удали» — отсюда."""
    items = await topic_list().repository.items()
    views = view_store()
    view = views.new_view([item.id for item in items])
    pages = list_pages(items, locale)
    for index, page in enumerate(pages):
        markup = page_markup(view, page, locale, last=index == len(pages) - 1, private=private)
        await bot.send_message(chat_id=chat_id, text=page.text, reply_markup=markup, link_preview_options=NO_PREVIEW)
    # Снимок запоминается после показа: если отправка сорвалась, «удали N»
    # по-прежнему относится к списку, который человек видит целиком.
    await views.remember(chat_id, view)
    report_list_size(items)
    return view


def numbered_lines(title: str, numbered: list[tuple[int, Item]], locale: str) -> str:
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
        text = t("topics_numbers_unknown", locale, numbers=numbers_text(unknown), total=len(view.ids))
        await bot.send_message(chat_id=chat_id, text=text)
        return
    by_id = {view.item_id(number): number for number in numbers}
    removed = await topic_list(bot).remove(list(by_id), moderator_id=user_id)
    gone = sorted(set(numbers) - {by_id[item.id] for item in removed})
    for item in removed:
        count_event(metrics, "topic_removed", kind=item.kind.value)
    logger.info(f"topics: removed {[item.id for item in removed]} by {user_id}, already gone: {gone}")
    if not removed:
        await bot.send_message(chat_id=chat_id, text=t("topics_removed_nothing", locale, numbers=numbers_text(gone)))
    else:
        text = numbered_lines(t("topics_removed", locale), [(by_id[item.id], item) for item in removed], locale)
        if gone:
            text += "\n" + t("topics_removed_gone", locale, numbers=numbers_text(gone))
        undo = await views.keep_removed([item.id for item in removed])
        markup = InlineKeyboardMarkup(inline_keyboard=[[_control("topics_undo", UNDO, locale, undo)]])
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, link_preview_options=NO_PREVIEW)
    await send_list(bot, chat_id, locale, private=private)


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
