"""Что бот показывает ведущим про список тем и вопросов.

Сообщения списка с кнопками и панель авторов. Отдельного отчёта об удалении
нет: под списком на время отмены стоит строка «Удалил: 1, 3» и кнопка
«Вернуть». Кто и когда это вызывает, решает :mod:`handlers.topics_list_handler`.
"""

from collections import Counter
from html import escape
from typing import Any

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, MaybeInaccessibleMessage
from loguru import logger

from config import TIMEZONE
from services.i18n import t
from services.topics.listing import MARK as MARKED_PREFIX
from services.topics.listing import Page, item_line, list_pages, table_html
from services.topics.runtime import count_event, report_list_size, topic_list, view_store
from services.topics.views import ListView, Removal
from utils import rich

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


def _remove_button(view: ListView, locale: str) -> InlineKeyboardButton:
    """«Удалить отмеченные (N)»: число показывает, сколько пунктов уйдёт."""
    label = MARKED_PREFIX + t("topics_remove_marked", locale, count=len(view.marked))
    return InlineKeyboardButton(text=label, callback_data=ListCallback(a=REMOVE, v=view.token).pack())


def page_markup(
    view: ListView, page: Page, locale: str, *, last: bool, private: bool, undo: str | None = None
) -> InlineKeyboardMarkup | None:
    """Кнопки под сообщением списка: номера его пунктов, а под последним ещё
    и действия со списком. *undo*: метка удаления, которое можно вернуть."""
    numbers = [_number_button(view, number) for number in page.numbers]
    rows = [numbers[i : i + NUMBERS_PER_ROW] for i in range(0, len(numbers), NUMBERS_PER_ROW)]
    if last:
        if undo:
            rows.append([_control("topics_undo", UNDO, locale, undo)])
        refresh = _control("topics_refresh", REFRESH, locale)
        rows.append([_remove_button(view, locale), refresh] if view.ids else [refresh])
        if private:
            # Авторы и бан живут в разделе «Темы и вопросы» главного меню:
            # под списком только то, что нужно, пока его читают.
            rows.append(
                [
                    _control("topics_add_topic", ADD_TOPIC, locale),
                    _control("topics_add_question", ADD_QUESTION, locale),
                ]
            )
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def remark(markup: InlineKeyboardMarkup, view: ListView, locale: str) -> InlineKeyboardMarkup:
    """Та же клавиатура с отметками из *view*: на кнопках номеров и в счётчике
    «Удалить отмеченные (N)»."""
    prefix = f"{ListCallback.__prefix__}:"

    def relabel(button: InlineKeyboardButton) -> InlineKeyboardButton:
        data = button.callback_data or ""
        if data.startswith(f"{prefix}{MARK}:"):
            return _number_button(view, ListCallback.unpack(data).n)
        if data.startswith(f"{prefix}{REMOVE}:"):
            return _remove_button(view, locale)
        return button

    return InlineKeyboardMarkup(
        inline_keyboard=[[relabel(button) for button in row] for row in markup.inline_keyboard]
    )


def last_page_markup(
    view: ListView, locale: str, *, private: bool, undo: str | None = None
) -> InlineKeyboardMarkup | None:
    """Клавиатура последнего сообщения списка под текущие отметки."""
    return page_markup(view, Page("", view.last_numbers), locale, last=True, private=private, undo=undo)


def removal_line(removal: Removal, locale: str) -> str:
    """«Удалил: 1, 3»: стоит под списком, пока удаление можно вернуть."""
    return t("topics_removed", locale, numbers=numbers_text(removal.numbers))


def with_footer(page: Page, lines: list[str]) -> Page:
    """Сообщение списка со строками под ним: что удалено, что вернули."""
    if not lines:
        return page
    html = page.html + "".join(f"<p>{escape(line)}</p>" for line in lines)
    return Page(page.text + "\n\n" + "\n".join(escape(line) for line in lines), page.numbers, html)


def marked_text(view: ListView, locale: str) -> str:
    """Всплывающий ответ на отметку; он не длиннее 200 символов."""
    if not view.marked:
        return t("topics_marked_none", locale)
    text = t("topics_marked", locale, numbers=numbers_text(view.marked))
    return text if len(text) <= MAX_TOAST_CHARS else t("topics_marked_count", locale, count=len(view.marked))


async def send_list(
    bot: Bot,
    chat_id: int,
    locale: str,
    *,
    private: bool,
    replace: MaybeInaccessibleMessage | None = None,
    note: str | None = None,
) -> ListView:
    """Показать список и запомнить его: номера следующей команды «удали» — отсюда.

    *replace*: сообщение прежнего списка. Если новый список умещается в одно
    сообщение, он рисуется на его месте, а не присылается следом: кнопки
    «Обновить», «Удалить отмеченные» и «Вернуть» не двигают чат.

    *note*: строка под списком на один показ («Вернул: 2», «уже были
    удалены»). Строку «Удалил: …» и кнопку «Вернуть» список рисует сам, пока
    последнее удаление в чате можно отменить.
    """
    items = await topic_list().repository.items()
    views = view_store()
    view = views.new_view([item.id for item in items])
    pages = list_pages(items, locale, timezone=TIMEZONE)
    removal = await views.pending_removal(chat_id)
    footer = ([removal_line(removal, locale)] if removal else []) + ([note] if note else [])
    pages[-1] = with_footer(pages[-1], footer)
    undo = removal.token if removal else None
    in_place = replace is not None and len(pages) == 1
    for index, page in enumerate(pages):
        last = index == len(pages) - 1
        markup = page_markup(view, page, locale, last=last, private=private, undo=undo if last else None)
        if in_place:
            await rich.edit(bot, chat_id, replace.message_id, page.html, page.text, markup)
            message_id = replace.message_id
        else:
            sent = await rich.send(bot, chat_id, page.html, page.text, markup)
            message_id = sent.message_id
    view.last_message_id, view.last_numbers = int(message_id), pages[-1].numbers
    # Снимок запоминается после показа: если отправка сорвалась, «удали N»
    # по-прежнему относится к списку, который человек видит целиком.
    await views.remember(chat_id, view)
    report_list_size(items)
    return view


async def marked_page(view: ListView, numbers: list[int], locale: str, removal: Removal | None = None) -> Page:
    """Сообщение списка с пунктами *numbers* под текущие отметки *view*.

    Пункт, который уже удалили из другого места, остаётся строкой с тем же
    номером: номера показанного списка не сдвигаются. *removal*: удаление,
    строка о котором стоит под этим сообщением.
    """
    by_id = {item.id: item for item in await topic_list().repository.items()}
    numbered = [(number, by_id[view.item_id(number)]) for number in numbers if view.item_id(number) in by_id]
    title = bool(numbers) and numbers[0] == 1
    lines = [t("topics_list_title", locale)] if title else []
    for number, item in numbered:
        if number in view.marked:
            lines.append(f"{MARKED_PREFIX}{number}) <s>{item_line(number, item, locale).split(') ', 1)[1]}</s>")
        else:
            lines.append(item_line(number, item, locale))
    html = table_html(numbered, view.marked, locale, title=title, timezone=TIMEZONE)
    page = Page("\n".join(lines), [number for number, _item in numbered], html)
    return with_footer(page, [removal_line(removal, locale)] if removal else [])


async def remove_numbers(
    bot: Bot,
    chat_id: int,
    user_id: int,
    numbers: list[int],
    locale: str,
    *,
    private: bool,
    metrics: Any,
    replace: MaybeInaccessibleMessage | None = None,
) -> None:
    """Удалить пункты по номерам последнего показанного списка и показать остаток.

    Ответ один: свежий список, под ним «Удалил: 1, 3» и кнопка «Вернуть».
    *replace*: сообщение списка, под которым нажали кнопку: остаток рисуется
    на его месте.
    """
    views = view_store()
    view = await views.last(chat_id)
    if view is None:
        await send_list(bot, chat_id, locale, private=private, replace=replace, note=t("topics_view_missing", locale))
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
    note = None
    if not removed:
        note = t("topics_removed_nothing", locale, numbers=numbers_text(gone))
    else:
        await views.keep_removed(chat_id, [item.id for item in removed], sorted(by_id[item.id] for item in removed))
        if gone:
            note = t("topics_removed_gone", locale, numbers=numbers_text(gone))
    await send_list(bot, chat_id, locale, private=private, replace=replace, note=note)


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
