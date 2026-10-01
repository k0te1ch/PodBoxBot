"""Вариант D: голосование слушателей по темам из очереди.

``/admin`` → «Темы слушателей» → «Голосования»:

* «Новое голосование»: ведущий отмечает от 3 до 5 тем из новых и отложенных
  и публикует нативный опрос Telegram в ``TOPICS_POLL_CHAT``. Опрос
  анонимный и открыт ``TOPICS_POLL_HOURS`` часов (0 — до закрытия вручную).
* Карточка голосования: варианты с голосами и кнопка «Закрыть опрос».

Telegram присылает боту апдейт ``poll`` о каждом голосе в его опросах и о
закрытии через ``stopPoll``: по нему обновляются голоса и подводится итог.
Об опросе, который истёк сам (``open_period``), Telegram боту не сообщает,
поэтому бот раз в минуту сам ищет такие опросы (:func:`watch_polls`) и
подводит итог по последним голосам. Победитель переходит в «Взята в выпуск»,
автору уходит уведомление, админам — итог. Ничья решается в пользу темы,
которая стоит в опросе выше; без голосов победителя нет.
"""

import asyncio
import html
import os
import time
from datetime import datetime
from typing import Any

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputPollOption, Poll
from loguru import logger
from sagenza_tgbot_sdk.menus import Button, ListItem, ListMenu, MenuContext, Submenu
from sagenza_tgbot_sdk.menus.callback import Action, MenuCallback

import config as bot_config
from filters.dispatcher_filters import IsAdmin
from handlers.topics_handler import notify_status, preview
from services.i18n import t
from services.topics import Topic, TopicPoll, TopicStatus
from services.topics.runtime import count_event, poll_store, topic_service, topics_enabled

POLLS_MENU = "topics_polls"
PICK_MENU = "topics_poll_pick"
PICK_STATE_KEY = "topics_poll_pick"

MIN_OPTIONS = 3
MAX_OPTIONS = 5
# Лимиты Bot API: вариант опроса — до 100 символов, open_period — до 2628000 с.
OPTION_CHARS = 100
MAX_OPEN_SECONDS = 2_628_000
CANDIDATES_LIMIT = 50
# Как часто бот ищет опросы, у которых вышло время.
WATCH_SECONDS = 60


class PollCallback(CallbackData, prefix="tpp"):
    a: str
    id: int
    p: int = 0


def _state(ctx: MenuContext) -> FSMContext | None:
    state = ctx.data.get("state")
    return state if isinstance(state, FSMContext) else None


async def _picked(ctx: MenuContext) -> list[int]:
    state = _state(ctx)
    if state is None:
        return []
    return [int(topic_id) for topic_id in (await state.get_data()).get(PICK_STATE_KEY, [])]


async def _set_picked(ctx: MenuContext, picked: list[int]) -> None:
    state = _state(ctx)
    if state is not None:
        await state.update_data({PICK_STATE_KEY: picked})


# --- выбор тем --------------------------------------------------------------


async def candidates() -> list[Topic]:
    """Новые и отложенные темы, свежие сверху: из них собирается опрос."""
    repository = topic_service().repository
    topics = [
        *await repository.list(TopicStatus.NEW, CANDIDATES_LIMIT),
        *await repository.list(TopicStatus.LATER, CANDIDATES_LIMIT),
    ]
    return sorted(topics, key=lambda topic: topic.created_at, reverse=True)[:CANDIDATES_LIMIT]


async def _pick_items(ctx: MenuContext) -> list[ListItem]:
    picked = set(await _picked(ctx))
    return [
        ListItem(id=str(topic.id), text=f"{'☑️' if topic.id in picked else '▫️'} {preview(topic.text, 40)}")
        for topic in await candidates()
    ]


async def _toggle(ctx: MenuContext) -> None:
    topic_id = int(ctx.value or 0)
    picked = await _picked(ctx)
    if topic_id in picked:
        picked.remove(topic_id)
    elif len(picked) >= MAX_OPTIONS:
        await ctx.answer(ctx.text("topics_poll_too_many", max=MAX_OPTIONS), alert=True)
    else:
        picked.append(topic_id)
    await _set_picked(ctx, picked)
    await ctx.show(PICK_MENU, ctx.page)


async def _clear(ctx: MenuContext) -> None:
    await _set_picked(ctx, [])
    await ctx.answer()
    await ctx.show(PICK_MENU)


def _open_period() -> int | None:
    hours = int(bot_config.TOPICS_POLL_HOURS)
    return min(hours * 3600, MAX_OPEN_SECONDS) if hours > 0 else None


async def publish(ctx: MenuContext) -> None:
    """Опубликовать опрос из отмеченных тем."""
    repository = topic_service().repository
    topics = [topic for topic_id in await _picked(ctx) if (topic := await repository.get(topic_id)) is not None]
    topics = [topic for topic in topics if topic.status in (TopicStatus.NEW, TopicStatus.LATER)]
    if not MIN_OPTIONS <= len(topics) <= MAX_OPTIONS:
        await ctx.answer(ctx.text("topics_poll_pick_count", min=MIN_OPTIONS, max=MAX_OPTIONS), alert=True)
        return
    bot: Bot = ctx.data["bot"]
    options = [preview(topic.text, OPTION_CHARS) for topic in topics]
    period = _open_period()
    try:
        message = await bot.send_poll(
            chat_id=bot_config.TOPICS_POLL_CHAT,
            question=t("topics_poll_question"),
            options=[InputPollOption(text=option) for option in options],
            is_anonymous=True,
            open_period=period,
        )
    except TelegramAPIError as error:
        logger.error(f"topic poll to {bot_config.TOPICS_POLL_CHAT} failed: {error!r}")
        await ctx.answer(ctx.text("topics_poll_publish_failed"), alert=True)
        return
    poll = await poll_store().add(
        TopicPoll(
            topic_ids=[topic.id for topic in topics],
            options=options,
            chat_id=message.chat.id,
            message_id=message.message_id,
            poll_id=message.poll.id,
            votes=[0] * len(options),
            closes_at=time.time() + period if period else None,
        )
    )
    logger.info(f"topic poll #{poll.id} published: topics {poll.topic_ids}")
    count_event(ctx.data.get("metrics"), "topic_poll", action="published")
    await _set_picked(ctx, [])
    await ctx.answer(ctx.text("topics_poll_published"))
    await ctx.show(POLLS_MENU)


# --- голосования и итог -----------------------------------------------------


def _when(timestamp: float) -> str:
    return f"{datetime.fromtimestamp(timestamp, bot_config.TIMEZONE):%d.%m.%Y %H:%M}"


def _poll_line(poll: TopicPoll, ctx: MenuContext) -> str:
    day = f"{datetime.fromtimestamp(poll.created_at, bot_config.TIMEZONE):%d.%m}"
    if not poll.closed:
        return ctx.text("topics_poll_line_open", date=day, votes=poll.total_votes)
    if poll.winner_id is None:
        return ctx.text("topics_poll_line_no_winner", date=day)
    winner = poll.options[poll.topic_ids.index(poll.winner_id)]
    return ctx.text("topics_poll_line_closed", date=day, winner=preview(winner, 30))


async def _poll_items(ctx: MenuContext) -> list[ListItem]:
    return [ListItem(id=str(poll.id), text=_poll_line(poll, ctx)) for poll in await poll_store().list()]


def poll_card(poll: TopicPoll, ctx: MenuContext) -> str:
    status = (
        ctx.text("topics_poll_closed", date=_when(poll.closed_at)) if poll.closed else ctx.text("topics_poll_open")
    )
    lines = [f"<b>{ctx.text('topics_poll_card_title', id=poll.id)}</b> · {status}", _when(poll.created_at), ""]
    for index, (option, votes) in enumerate(zip(poll.options, poll.votes, strict=False)):
        mark = "🏆 " if poll.closed and poll.winner_id == poll.topic_ids[index] else ""
        lines.append(f"{index + 1}. {mark}{html.escape(option)} · {ctx.text('topics_poll_votes', count=votes)}")
    if poll.closed:
        lines.append("")
        if poll.winner_id is None:
            lines.append(ctx.text("topics_poll_no_winner"))
        elif poll.is_tie():
            lines.append(ctx.text("topics_poll_tie"))
    return "\n".join(lines)


def _card_markup(poll: TopicPoll, ctx: MenuContext) -> InlineKeyboardMarkup:
    rows = []
    if not poll.closed:
        close = PollCallback(a="close", id=poll.id, p=ctx.page).pack()
        rows.append([InlineKeyboardButton(text=ctx.text("topics_poll_close"), callback_data=close)])
    back = MenuCallback(m=POLLS_MENU, a=Action.OPEN, p=ctx.page).pack()
    rows.append([InlineKeyboardButton(text=ctx.text("menu-back"), callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _open_poll(ctx: MenuContext) -> None:
    poll = await poll_store().get(int(ctx.value or 0))
    if poll is None:
        await ctx.answer(ctx.text("topics_missing"), alert=True)
        await ctx.show(POLLS_MENU, ctx.page)
        return
    await ctx.answer()
    await ctx.put(poll_card(poll, ctx), _card_markup(poll, ctx))


async def finish(bot: Bot, poll: TopicPoll, metrics: Any = None) -> bool:
    """Подвести итог: победитель в «Взята в выпуск», автору и админам — весть.

    ``False``, если итог уже подвёл кто-то другой.
    """
    store = poll_store()
    if not await store.claim_close(poll.id):
        return False
    poll.closed_at = time.time()
    index = poll.leader()
    winner = None
    if index is not None:
        poll.winner_id = poll.topic_ids[index]
        change = await topic_service().set_status(poll.winner_id, TopicStatus.TAKEN)
        if change is not None:
            winner = change.topic
            if change.changed:
                count_event(metrics, "topic_status", status=TopicStatus.TAKEN)
                await notify_status(bot, winner)
    await store.save(poll)
    count_event(metrics, "topic_poll", action="closed")
    logger.info(f"topic poll #{poll.id} closed, votes {poll.votes}, winner {poll.winner_id}")
    await _tell_admins(bot, poll, winner)
    return True


async def _stop(bot: Bot, poll: TopicPoll) -> None:
    """Закрыть опрос в Telegram и взять из ответа окончательные голоса."""
    try:
        final = await bot.stop_poll(chat_id=poll.chat_id, message_id=poll.message_id)
        poll.votes = [option.voter_count for option in final.options]
    except TelegramBadRequest as error:
        # Уже закрыт (истёк) или сообщение удалили — итог по последним голосам.
        logger.info(f"stop topic poll #{poll.id}: {error!r}")


async def close_due_polls(bot: Bot, metrics: Any = None) -> int:
    """Подвести итог опросов, у которых вышло время; сколько закрыто."""
    closed = 0
    for poll in await poll_store().due(time.time()):
        await _stop(bot, poll)
        closed += await finish(bot, poll, metrics)
    return closed


async def watch_polls(bot: Bot, metrics: Any = None, interval: float = WATCH_SECONDS) -> None:
    """Фоновая задача: закрывает опросы по таймеру, пока бот работает."""
    while True:
        try:
            await close_due_polls(bot, metrics)
        except Exception as error:
            logger.warning(f"topic polls: closing due polls failed: {error!r}")
        await asyncio.sleep(interval)


async def _tell_admins(bot: Bot, poll: TopicPoll, winner: Topic | None) -> None:
    if winner is None:
        text = t("topics_poll_result_none", id=poll.id)
    else:
        text = t("topics_poll_result", id=poll.id, topic=html.escape(preview(winner.text, 80)), votes=max(poll.votes))
    for admin_id in bot_config.ADMINS_ID:
        try:
            await bot.send_message(chat_id=admin_id, text=text)
        except TelegramAPIError as error:
            logger.warning(f"topic poll result to admin {admin_id} failed: {error!r}")


router = Router(name=os.path.splitext(os.path.basename(__file__))[0])


@router.poll(topics_enabled)
async def on_poll_update(poll: Poll, bot: Bot, metrics: Any = None):
    """Голоса и закрытие опросов бота: Telegram шлёт их без запроса."""
    store = poll_store()
    stored = await store.by_telegram_id(poll.id)
    if stored is None or stored.closed:
        return
    stored.votes = [option.voter_count for option in poll.options]
    if poll.is_closed:
        await finish(bot, stored, metrics)
    else:
        await store.save(stored)


@router.callback_query(PollCallback.filter(), IsAdmin)
async def close_poll(
    callback: CallbackQuery, callback_data: PollCallback, state: FSMContext, bot: Bot, metrics: Any = None
):
    from handlers.menus import menus

    ctx = menus.context(callback, {"state": state})
    stored = await poll_store().get(callback_data.id)
    if stored is None:
        await ctx.answer(ctx.text("topics_missing"), alert=True)
        await ctx.show(POLLS_MENU, callback_data.p)
        return
    if not stored.closed:
        await _stop(bot, stored)
        await finish(bot, stored, metrics)
    await ctx.answer(ctx.text("topics_poll_closed_toast"))
    fresh = await poll_store().get(stored.id)
    ctx.page = callback_data.p
    await ctx.put(poll_card(fresh, ctx), _card_markup(fresh, ctx))


def polls_submenu() -> Submenu:
    """«Голосования» под списком статусов тем."""
    pick = ListMenu(
        PICK_MENU,
        source=_pick_items,
        on_select=_toggle,
        title=PICK_MENU,
        page_size=8,
        items=[
            Button("topics_poll_publish", id="publish", handler=publish, confirm=True),
            Button("topics_poll_clear", id="clear", handler=_clear),
        ],
    )
    polls = ListMenu(
        POLLS_MENU,
        source=_poll_items,
        on_select=_open_poll,
        title=POLLS_MENU,
        page_size=8,
        items=[Submenu("topics_poll_new", pick, id="new")],
    )
    return Submenu("topics_polls_button", polls, id="polls")
