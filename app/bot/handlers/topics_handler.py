"""Темы от слушателей: приём по хештегу в чате и очередь для ведущих.

* Сообщение с ``#тема`` (``TOPICS_HASHTAG``) в чате тем (``TOPICS_CHAT``)
  становится темой. Принятую бот отмечает реакцией 👍, при отказе (лимит,
  длина, бан) отвечает автору эфемерно: это видит только он.
* ``/admin`` → «Темы слушателей»: статусы со счётчиками → список тем
  постранично → карточка с кнопками «Взять в выпуск», «Отклонить», «Позже»
  и «Заблокировать автора». «Взять в выпуск» спрашивает номер выпуска
  (можно и без номера), он уходит автору в уведомлении.

Все пути приёма (хештег, анкета, ``/тема`` в личке, опрос) пишут в одну
очередь модуля ``suggest`` SDK, разбор только здесь: карточки SDK выключены.
Всё работает, только когда включён ``TOPICS_ENABLED``. Хранилище и проверки —
в :mod:`services.topics`, здесь только Telegram.
"""

import html
import os
import time
from datetime import datetime
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReactionTypeEmoji
from loguru import logger
from sagenza_tgbot_sdk.menus import ListItem, ListMenu, MenuContext, Submenu
from sagenza_tgbot_sdk.menus.callback import Action, MenuCallback

import config as bot_config
from filters.dispatcher_filters import IsAdmin
from services.collector import pick_tag, strip_hashtags
from services.i18n import t
from services.topics import Refusal, StatusChange, Suggestion, Topic, TopicSource, TopicStatus
from services.topics.delivery import notify_author, send_ephemeral
from services.topics.runtime import (
    author_of,
    count_event,
    is_topics_chat,
    message_link,
    suggest_texts,
    topic_service,
    topics_enabled,
)
from utils.menu_context import only_inside

STATUSES_MENU = "topics"
ENTRIES_MENU = "topics_entries"
STATE_KEY = "topics_status"
EPISODE_TOPIC_KEY = "topics_episode_topic"
EPISODE_PAGE_KEY = "topics_episode_page"
EPISODE_ASKED_KEY = "topics_episode_asked"

STATUS_ORDER = (TopicStatus.NEW, TopicStatus.LATER, TopicStatus.TAKEN, TopicStatus.REJECTED)
# Кнопки карточки: во что можно перевести тему. Текущий статус не показывается.
DECISIONS = {
    TopicStatus.TAKEN: "topics_take",
    TopicStatus.REJECTED: "topics_reject",
    TopicStatus.LATER: "topics_later",
}
# Действия карточки кроме смены статуса: «Взять в выпуск» сначала спрашивает
# номер выпуска, из вопроса можно вернуться к карточке.
ASK_EPISODE = "episode"
CARD = "card"
BAN = "ban"
UNBAN = "unban"

LIST_PREVIEW_CHARS = 40
NOTICE_PREVIEW_CHARS = 60
EPISODE_MAX_CHARS = 20
# Сколько бот ждёт номер выпуска. Дольше нельзя: диалог загрузки выпуска
# не ставит состояние FSM, и забытый вопрос съел бы его короткий ответ.
EPISODE_WAIT_SECONDS = 10 * 60


class TopicCallback(CallbackData, prefix="tpc"):
    a: str
    id: int
    p: int = 0


class TopicStates(StatesGroup):
    episode = State()


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
    """Лог и метрика отказа, общие для хештега и анкеты.

    Принятую тему считает сама очередь SDK (``suggestion_submitted``).
    """
    if result.topic is not None:
        logger.info(f"topic #{result.topic.id} suggested via {source} by {result.topic.author.name}")
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
    result = await topic_service(bot, metrics).suggest(topic)
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


def card_text(topic: Topic, ctx: MenuContext, banned: bool = False) -> str:
    when = datetime.fromtimestamp(topic.created_at, bot_config.TIMEZONE)
    lines = [
        f"<b>{ctx.text('topics_card_title', id=topic.id)}</b> · {ctx.text(f'topics_status_{topic.status}')}",
        f"{html.escape(topic.author.name)} · {when:%d.%m.%Y %H:%M} · {ctx.text(f'topics_source_{topic.source}')}",
    ]
    if topic.note:
        lines.append(ctx.text("topics_card_episode", note=html.escape(topic.note)))
    if banned:
        lines.append(ctx.text("topics_card_banned"))
    lines += ["", html.escape(topic.text)]
    if topic.link:
        lines += ["", f'<a href="{html.escape(topic.link)}">{ctx.text("topics_open_message")}</a>']
    return "\n".join(lines)


def _button(ctx: MenuContext, key: str, action: str, topic_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=ctx.text(key), callback_data=TopicCallback(a=action, id=topic_id, p=ctx.page).pack()
    )


def _back_row(ctx: MenuContext) -> list[InlineKeyboardButton]:
    back = MenuCallback(m=ENTRIES_MENU, a=Action.OPEN, p=ctx.page).pack()
    return [InlineKeyboardButton(text=ctx.text("menu-back"), callback_data=back)]


def card_markup(topic: Topic, ctx: MenuContext, banned: bool = False) -> InlineKeyboardMarkup:
    decisions = [
        _button(ctx, key, ASK_EPISODE if status is TopicStatus.TAKEN else status.value, topic.id)
        for status, key in DECISIONS.items()
        if status != topic.status
    ]
    rows = [decisions]
    if topic.author.user_id is not None:
        rows.append([_button(ctx, "topics_unban" if banned else "topics_ban", UNBAN if banned else BAN, topic.id)])
    rows.append(_back_row(ctx))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _put_card(ctx: MenuContext, topic: Topic) -> None:
    user_id = topic.author.user_id
    banned = user_id is not None and await topic_service().repository.is_banned(user_id)
    await ctx.put(card_text(topic, ctx, banned), card_markup(topic, ctx, banned))


async def _open_topic(ctx: MenuContext) -> None:
    topic = await topic_service().repository.get(int(ctx.value or 0))
    if topic is None:
        await ctx.answer(ctx.text("topics_missing"), alert=True)
        await ctx.show(ENTRIES_MENU, ctx.page)
        return
    await ctx.answer()
    await _put_card(ctx, topic)


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
        items=[Submenu(ENTRIES_MENU, entries, id="entries", visible_if=only_inside(ENTRIES_MENU)), *extra_items],
    )


def topics_submenu(visible_if, extra_items: tuple = ()) -> Submenu:
    """Пункт админ-панели: виден админам, когда фича включена."""
    return Submenu(
        "admin_topics",
        build_topics_menu(extra_items),
        id="topics",
        visible_if=lambda ctx: topics_enabled() and visible_if(ctx),
    )


# --- решения по карточке ----------------------------------------------------


async def _leave_episode_question(state: FSMContext) -> None:
    if await state.get_state() == TopicStates.episode.state:
        await state.set_state(None)


async def _ask_episode(ctx: MenuContext, state: FSMContext, topic: Topic) -> None:
    await state.set_state(TopicStates.episode)
    await state.update_data({EPISODE_TOPIC_KEY: topic.id, EPISODE_PAGE_KEY: ctx.page, EPISODE_ASKED_KEY: time.time()})
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(ctx, "topics_take_without_episode", TopicStatus.TAKEN.value, topic.id)],
            [_button(ctx, "menu-back", CARD, topic.id)],
        ]
    )
    await ctx.answer()
    await ctx.put(ctx.text("topics_ask_episode", id=topic.id, max=EPISODE_MAX_CHARS), markup)


async def _toggle_ban(ctx: MenuContext, topic: Topic, action: str) -> None:
    repository = topic_service().repository
    user_id = topic.author.user_id
    if action == BAN:
        await repository.ban(user_id)
    else:
        await repository.unban(user_id)
    logger.info(f"topic author {user_id}: {action} from topic #{topic.id}")
    count_event(ctx.data.get("metrics"), "topic_author", action=action)
    await ctx.answer(ctx.text(f"topics_{action}_done"))
    await _put_card(ctx, topic)


async def _card_action(ctx: MenuContext, state: FSMContext, action: str, topic_id: int) -> None:
    """Вопрос о номере выпуска, возврат к карточке, бан и разбан."""
    topic = await topic_service().repository.get(topic_id)
    if topic is None:
        await ctx.answer(ctx.text("topics_missing"), alert=True)
        await ctx.show(ENTRIES_MENU, ctx.page)
    elif action == ASK_EPISODE:
        await _ask_episode(ctx, state, topic)
    elif action in (BAN, UNBAN) and topic.author.user_id is not None:
        await _toggle_ban(ctx, topic, action)
    else:
        await ctx.answer()
        await _put_card(ctx, topic)


async def _apply(
    bot: Bot, metrics: Any, topic_id: int, status: TopicStatus, moderator_id: int, note: str | None = None
) -> StatusChange | None:
    change = await topic_service(bot, metrics).set_status(topic_id, status, note=note, moderator_id=moderator_id)
    if change is not None and change.changed:
        logger.info(f"topic #{topic_id}: {change.previous} -> {change.topic.status} {note or ''}".rstrip())
        await notify_status(bot, change.topic)
    return change


@router.callback_query(TopicCallback.filter(), IsAdmin)
async def decide(
    callback: CallbackQuery, callback_data: TopicCallback, state: FSMContext, bot: Bot, metrics: Any = None
):
    from handlers.menus import menus

    ctx = menus.context(callback, {"state": state, "metrics": metrics})
    ctx.page = callback_data.p
    if callback_data.a in (ASK_EPISODE, CARD, BAN, UNBAN):
        if callback_data.a != ASK_EPISODE:
            await _leave_episode_question(state)
        await _card_action(ctx, state, callback_data.a, callback_data.id)
        return
    decision = parse_status(callback_data.a)
    if decision not in DECISIONS:
        await ctx.answer()
        return
    await _leave_episode_question(state)
    change = await _apply(bot, metrics, callback_data.id, decision, callback.from_user.id)
    if change is None:
        await ctx.answer(ctx.text("topics_missing"), alert=True)
    else:
        await ctx.answer(ctx.text(f"topics_marked_{change.topic.status}"))
    await ctx.show(ENTRIES_MENU, callback_data.p)


async def _is_episode_answer(message: Message, state: FSMContext) -> bool:
    """Короткий текст вскоре после вопроса о номере; остальное идёт мимо, к
    другим хендлерам, а не пропадает в ответе «не похоже на номер»."""
    asked = float((await state.get_data()).get(EPISODE_ASKED_KEY, 0))
    return time.time() - asked <= EPISODE_WAIT_SECONDS and len(" ".join(message.text.split())) <= EPISODE_MAX_CHARS


@router.message(
    TopicStates.episode, F.chat.type == ChatType.PRIVATE, F.text, ~F.text.startswith("/"), IsAdmin, _is_episode_answer
)
async def take_with_episode(msg: Message, state: FSMContext, bot: Bot, metrics: Any = None):
    """Номер выпуска для темы, которую ведущий берёт из карточки."""
    from handlers.menus import menus

    ctx = menus.context(msg, {"state": state, "metrics": metrics})
    episode = " ".join(msg.text.split())
    data = await state.get_data()
    await state.set_state(None)
    ctx.page = int(data.get(EPISODE_PAGE_KEY, 0))
    change = await _apply(
        bot, metrics, int(data.get(EPISODE_TOPIC_KEY, 0)), TopicStatus.TAKEN, msg.from_user.id, note=episode
    )
    if change is None:
        await msg.answer(ctx.text("topics_missing"))
        return
    await msg.answer(ctx.text("topics_marked_taken_episode", note=html.escape(episode)))
    await _put_card(ctx, change.topic)


def status_notice(topic: Topic) -> str:
    """Уведомление автору: ключи ``suggest-notify-*`` модуля SDK, у бота свои тексты.

    Вариант ``-note``, когда у темы есть номер выпуска.
    """
    key = f"suggest-notify-{topic.status}" + ("-note" if topic.note else "")
    return suggest_texts()(
        key,
        topic.author.language,
        id=topic.id,
        note=html.escape(topic.note or ""),
        text=html.escape(preview(topic.text, NOTICE_PREVIEW_CHARS)),
    )


async def notify_status(bot: Bot, topic: Topic) -> bool:
    """Короткое уведомление автору о новом статусе темы."""
    return await notify_author(bot, topic, status_notice(topic))
