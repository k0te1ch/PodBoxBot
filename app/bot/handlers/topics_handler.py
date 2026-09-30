"""Темы от слушателей: приём по хештегу в чате и очередь для ведущих.

* Сообщение с ``#тема`` (``TOPICS_HASHTAG``) в чате тем (``TOPICS_CHAT``)
  становится темой. Принятую бот отмечает реакцией 👍, при отказе (лимит,
  длина) отвечает автору эфемерно — это видит только он.
* ``/admin`` → «Темы слушателей»: статусы со счётчиками → список тем
  постранично → карточка с кнопками «Взять в выпуск», «Отклонить», «Позже».
  Автору уходит короткое уведомление о новом статусе.

Всё работает, только когда включён ``TOPICS_ENABLED``. Хранилище и проверки —
в :mod:`services.topics`, здесь только Telegram.
"""

import html
import os
from datetime import datetime
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReactionTypeEmoji
from loguru import logger
from sagenza_tgbot_sdk.menus import ListItem, ListMenu, MenuContext, Submenu
from sagenza_tgbot_sdk.menus.callback import Action, MenuCallback

import config as bot_config
from filters.dispatcher_filters import IsAdmin
from services.collector import pick_tag, strip_hashtags
from services.i18n import t
from services.topics import Refusal, Suggestion, Topic, TopicSource, TopicStatus
from services.topics.delivery import notify_author, send_ephemeral
from services.topics.runtime import (
    author_of,
    count_event,
    is_topics_chat,
    message_link,
    topic_service,
    topics_enabled,
)

STATUSES_MENU = "topics"
ENTRIES_MENU = "topics_entries"
STATE_KEY = "topics_status"

STATUS_ORDER = (TopicStatus.NEW, TopicStatus.LATER, TopicStatus.TAKEN, TopicStatus.REJECTED)
# Кнопки карточки: во что можно перевести тему. Текущий статус не показывается.
DECISIONS = {
    TopicStatus.TAKEN: "topics_take",
    TopicStatus.REJECTED: "topics_reject",
    TopicStatus.LATER: "topics_later",
}

LIST_PREVIEW_CHARS = 40
NOTICE_PREVIEW_CHARS = 60


class TopicCallback(CallbackData, prefix="tpc"):
    a: str
    id: int
    p: int = 0


def parse_status(value: Any) -> TopicStatus | None:
    try:
        return TopicStatus(value)
    except ValueError:
        return None


def preview(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def refusal_text(refusal: Refusal, locale: str) -> str:
    return t(
        f"topics_refused_{refusal}",
        locale,
        min=bot_config.TOPICS_MIN_LENGTH,
        max=bot_config.TOPICS_MAX_LENGTH,
        limit=bot_config.TOPICS_DAILY_LIMIT,
    )


def record_suggestion(result: Suggestion, source: TopicSource, metrics: Any) -> None:
    """Лог и метрика по итогу приёма темы — общие для хештега и анкеты."""
    if result.topic is not None:
        logger.info(f"topic #{result.topic.id} suggested via {source} by {result.topic.author.name}")
        count_event(metrics, "topic_suggested", source=source)
    elif result.refusal is not None:
        logger.info(f"topic via {source} refused: {result.refusal}")
        count_event(metrics, "topic_refused", reason=result.refusal)


# --- приём по хештегу -------------------------------------------------------


def _from_topics_chat(message: Message) -> bool:
    return is_topics_chat(message.chat)


def _has_topic_hashtag(message: Message) -> bool:
    hashtag = bot_config.TOPICS_HASHTAG
    return bool(hashtag) and pick_tag(message.text or message.caption, [hashtag]) is not None


router = Router(name=os.path.splitext(os.path.basename(__file__))[0])


@router.message(topics_enabled, _from_topics_chat, F.text | F.caption, _has_topic_hashtag)
async def collect_from_chat(msg: Message, bot: Bot, metrics: Any = None):
    topic = Topic(
        text=strip_hashtags(msg.text or msg.caption, [bot_config.TOPICS_HASHTAG]),
        author=author_of(msg),
        source=TopicSource.HASHTAG,
        chat_id=msg.chat.id,
        message_id=msg.message_id,
        link=message_link(msg.chat, msg.message_id),
    )
    result = await topic_service().suggest(topic)
    record_suggestion(result, TopicSource.HASHTAG, metrics)
    if result.topic is not None:
        try:
            await msg.react([ReactionTypeEmoji(emoji="👍")])
        except TelegramAPIError as error:
            logger.info(f"topic #{result.topic.id}: reaction failed: {error!r}")
        return
    author = topic.author
    if result.refusal is Refusal.DUPLICATE or author.user_id is None:
        return
    text = refusal_text(result.refusal, author.language)
    await send_ephemeral(bot, msg.chat.id, author.user_id, text, reply_to=msg.message_id)


# --- очередь в /admin -------------------------------------------------------


def _state(ctx: MenuContext) -> FSMContext | None:
    state = ctx.data.get("state")
    return state if isinstance(state, FSMContext) else None


async def _current_status(ctx: MenuContext) -> TopicStatus:
    state = _state(ctx)
    if state is not None:
        status = parse_status((await state.get_data()).get(STATE_KEY))
        if status is not None:
            return status
    return TopicStatus.NEW


async def _statuses(ctx: MenuContext) -> list[ListItem]:
    repository = topic_service().repository
    return [
        ListItem(id=status.value, text=f"{ctx.text(f'topics_status_{status}')} ({await repository.count(status)})")
        for status in STATUS_ORDER
    ]


async def _open_status(ctx: MenuContext) -> None:
    state = _state(ctx)
    if state is not None and parse_status(ctx.value) is not None:
        await state.update_data({STATE_KEY: ctx.value})
    await ctx.show(ENTRIES_MENU)


def _list_line(topic: Topic) -> str:
    return f"{datetime.fromtimestamp(topic.created_at, bot_config.TIMEZONE):%d.%m} {preview(topic.text, LIST_PREVIEW_CHARS)}"


async def _entries(ctx: MenuContext) -> list[ListItem]:
    topics = await topic_service().repository.list(await _current_status(ctx))
    return [ListItem(id=str(topic.id), text=_list_line(topic)) for topic in topics]


def card_text(topic: Topic, ctx: MenuContext) -> str:
    when = datetime.fromtimestamp(topic.created_at, bot_config.TIMEZONE)
    lines = [
        f"<b>{ctx.text('topics_card_title', id=topic.id)}</b> · {ctx.text(f'topics_status_{topic.status}')}",
        f"{html.escape(topic.author.name)} · {when:%d.%m.%Y %H:%M} · {ctx.text(f'topics_source_{topic.source}')}",
        "",
        html.escape(topic.text),
    ]
    if topic.link:
        lines += ["", f'<a href="{html.escape(topic.link)}">{ctx.text("topics_open_message")}</a>']
    return "\n".join(lines)


def card_markup(topic: Topic, ctx: MenuContext) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=ctx.text(key), callback_data=TopicCallback(a=status.value, id=topic.id, p=ctx.page).pack()
        )
        for status, key in DECISIONS.items()
        if status != topic.status
    ]
    back = MenuCallback(m=ENTRIES_MENU, a=Action.OPEN, p=ctx.page).pack()
    return InlineKeyboardMarkup(
        inline_keyboard=[buttons, [InlineKeyboardButton(text=ctx.text("menu-back"), callback_data=back)]]
    )


async def _open_topic(ctx: MenuContext) -> None:
    topic = await topic_service().repository.get(int(ctx.value or 0))
    if topic is None:
        await ctx.answer(ctx.text("topics_missing"), alert=True)
        await ctx.show(ENTRIES_MENU, ctx.page)
        return
    await ctx.answer()
    await ctx.put(card_text(topic, ctx), card_markup(topic, ctx))


def build_topics_menu(extra_items: tuple = ()) -> ListMenu:
    """Статусы → темы статуса. Темы — дочернее меню со скрытой кнопкой, как у
    заметок ведущих: «Назад» из него ведёт к статусам. *extra_items* —
    кнопки под списком статусов (анкета, голосования)."""
    entries = ListMenu(ENTRIES_MENU, source=_entries, on_select=_open_topic, title=ENTRIES_MENU, page_size=8)
    return ListMenu(
        STATUSES_MENU,
        source=_statuses,
        on_select=_open_status,
        title="topics_panel",
        items=[Submenu(ENTRIES_MENU, entries, id="entries", visible_if=lambda _ctx: False), *extra_items],
    )


def topics_submenu(visible_if) -> Submenu:
    """Пункт админ-панели: виден админам, когда фича включена."""
    return Submenu(
        "admin_topics",
        build_topics_menu(),
        id="topics",
        visible_if=lambda ctx: topics_enabled() and visible_if(ctx),
    )


@router.callback_query(TopicCallback.filter(), IsAdmin)
async def decide(
    callback: CallbackQuery, callback_data: TopicCallback, state: FSMContext, bot: Bot, metrics: Any = None
):
    from handlers.menus import menus

    ctx = menus.context(callback, {"state": state})
    decision = parse_status(callback_data.a)
    if decision not in DECISIONS:
        await ctx.answer()
        return
    change = await topic_service().set_status(callback_data.id, decision)
    if change is None:
        await ctx.answer(ctx.text("topics_missing"), alert=True)
    else:
        status = change.topic.status
        if change.changed:
            count_event(metrics, "topic_status", status=status)
            logger.info(f"topic #{change.topic.id}: {change.previous} -> {status}")
            await notify_status(bot, change.topic)
        await ctx.answer(ctx.text(f"topics_marked_{status}"))
    await ctx.show(ENTRIES_MENU, callback_data.p)


async def notify_status(bot: Bot, topic: Topic) -> bool:
    """Короткое уведомление автору о новом статусе темы."""
    text = t(
        f"topics_notice_{topic.status}",
        topic.author.language,
        topic=html.escape(preview(topic.text, NOTICE_PREVIEW_CHARS)),
    )
    return await notify_author(bot, topic, text)
