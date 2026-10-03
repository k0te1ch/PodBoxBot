"""Темы и вопросы из чата: сбор по хештегу и добавление админом по ответу.

* Сообщение с ``#тема`` или ``#вопрос`` (``TOPICS_HASHTAG``,
  ``TOPICS_QUESTION_HASHTAG``) в чате тем (``TOPICS_CHAT``) становится пунктом
  списка; тип пункта задаёт хештег. Принятое бот отмечает реакцией 👍
  (``TOPICS_ACK_REACTION``, эмодзи из ``TOPICS_ACK_EMOJI``) и пишет автору эфемерно, что добавил его в список
  (``TOPICS_ACK_EPHEMERAL``). При отказе (лимит, длина, бан) автор получает
  эфемерный ответ: это видит только он. Пост от имени канала считается по
  каналу: у него свой лимит, и его можно забанить.
* Админ отвечает на любое сообщение чата командой ``/тема`` или ``/вопрос``
  (``/topic``, ``/question``), и оно попадает в список без лимитов. Текст
  после команды заменяет текст сообщения. Команду от не-админа этот хендлер
  не видит: она открывает обычную анкету.

Всё работает, только когда включён ``TOPICS_ENABLED``. Хранилище и проверки —
в :mod:`services.topics`, здесь только Telegram.
"""

import os
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, ReactionTypeEmoji
from loguru import logger

import config as bot_config
from services.collector import extract_hashtags, strip_hashtags
from services.i18n import t
from services.topics import Added, Item, Kind, Refusal, Source
from services.topics.delivery import send_ephemeral
from services.topics.listing import item_text
from services.topics.runtime import (
    all_hashtags,
    author_of,
    count_event,
    is_admin,
    is_topics_chat,
    kind_of_hashtags,
    language_of,
    refresh_list_size,
    topic_list,
    topics_enabled,
)

TOPIC_COMMANDS = ("topic", "тема")
QUESTION_COMMANDS = ("question", "вопрос")


def kind_of_command(command: str) -> Kind:
    return Kind.QUESTION if command.lower() in QUESTION_COMMANDS else Kind.TOPIC


def refusal_text(refusal: Refusal, locale: str, *, trusted: bool = False) -> str:
    return t(
        f"topics_refused_{refusal}",
        locale,
        min=1 if trusted else bot_config.TOPICS_MIN_LENGTH,
        max=bot_config.TOPICS_MAX_LENGTH,
        limit=bot_config.TOPICS_DAILY_LIMIT,
    )


async def record_added(result: Added, kind: Kind, source: Source, metrics: Any) -> None:
    """Лог и метрики приёма, общие для хештега, анкеты и команд."""
    if result.item is not None:
        logger.info(f"topics: {kind} #{result.item.id} added via {source} by {result.item.author.name}")
        count_event(metrics, "topic_added", kind=kind.value, source=source.value)
        await refresh_list_size()
    elif result.refusal is not None:
        logger.info(f"topics: {kind} via {source} refused: {result.refusal}")
        count_event(metrics, "topic_refused", reason=result.refusal.value)


async def react(message: Message) -> None:
    """Реакция на сообщение, которое стало пунктом списка."""
    if not bot_config.TOPICS_ACK_REACTION:
        return
    try:
        await message.react([ReactionTypeEmoji(emoji=bot_config.TOPICS_ACK_EMOJI)])
    except TelegramAPIError as error:
        logger.info(f"topics: reaction on {message.message_id} failed: {error!r}")


def _from_topics_chat(message: Message) -> bool:
    return is_topics_chat(message.chat)


def _hashtag_kind(message: Message) -> dict[str, Kind] | bool:
    kind = kind_of_hashtags(extract_hashtags(message.text or message.caption))
    return {"kind": kind} if kind is not None else False


def _not_command(message: Message) -> bool:
    return not (message.text or message.caption or "").startswith("/")


def _visible(message: Message) -> bool:
    """Обычное сообщение чата. Эфемерное видит только бот: это ответ анкете
    или команда, а не реплика в чате, и ссылаться в нём не на что."""
    return message.ephemeral_message_id is None


def _is_reply(message: Message) -> bool:
    """Ответ на сообщение. В форуме любое сообщение темы «отвечает» на её
    служебное сообщение о создании: это не ответ."""
    target = message.reply_to_message
    return target is not None and target.forum_topic_created is None


router = Router(name=os.path.splitext(os.path.basename(__file__))[0])


@router.message(
    topics_enabled,
    _from_topics_chat,
    _is_reply,
    is_admin,
    Command(*TOPIC_COMMANDS, *QUESTION_COMMANDS, ignore_case=True),
)
async def add_by_reply(msg: Message, command: CommandObject, bot: Bot, metrics: Any = None):
    """Админ берёт в список сообщение, на которое ответил командой."""
    target = msg.reply_to_message
    kind = kind_of_command(command.command)
    locale = language_of(msg.from_user)
    item = Item(
        text=command.args or strip_hashtags(target.text or target.caption, all_hashtags()),
        kind=kind,
        author=author_of(target),
        source=Source.REPLY,
        chat_id=msg.chat.id,
        message_id=target.message_id,
    )
    result = await topic_list(bot).add(item, trusted=True)
    await record_added(result, kind, Source.REPLY, metrics)
    if result.item is not None:
        await react(target)
        answer = t("topics_admin_added", locale, line=item_text(result.item, locale))
    elif result.refusal is Refusal.TOO_SHORT:
        answer = t("topics_reply_no_text", locale)
    else:
        answer = refusal_text(result.refusal, locale, trusted=True)
    await _answer_admin(bot, msg, answer)


async def _answer_admin(bot: Bot, command: Message, text: str) -> None:
    """Ответ админу мимо чата: эфемерно, а если нельзя, то в личку. Саму
    команду бот убирает из чата, если может: слушателям она ни к чему."""
    admin_id = command.from_user.id
    if not await send_ephemeral(bot, command.chat.id, admin_id, text):
        try:
            await bot.send_message(chat_id=admin_id, text=text)
        except TelegramAPIError as error:
            logger.info(f"topics: admin {admin_id} is not reachable: {error!r}")
    if command.ephemeral_message_id is not None:
        return
    try:
        await command.delete()
    except TelegramAPIError as error:
        logger.debug(f"topics: could not delete the admin command: {error!r}")


@router.message(topics_enabled, _from_topics_chat, _visible, F.text | F.caption, _not_command, _hashtag_kind)
async def collect_from_chat(msg: Message, bot: Bot, kind: Kind, metrics: Any = None):
    """Сообщение с хештегом в чате тем. Админа лимит и бан не касаются."""
    trusted = is_admin(msg)
    item = Item(
        text=strip_hashtags(msg.text or msg.caption, all_hashtags()),
        kind=kind,
        author=author_of(msg),
        source=Source.HASHTAG,
        chat_id=msg.chat.id,
        message_id=msg.message_id,
    )
    result = await topic_list(bot).add(item, trusted=trusted)
    await record_added(result, kind, Source.HASHTAG, metrics)
    author = item.author
    if result.item is not None:
        await react(msg)
        if bot_config.TOPICS_ACK_EPHEMERAL and author.is_person:
            text = t(f"topics_added_{kind}", author.language)
            await send_ephemeral(bot, msg.chat.id, author.user_id, text, reply_to=msg.message_id)
        return
    # Каналу и анонимному админу эфемерно не ответить: отказ остаётся в логе.
    if result.refusal is Refusal.DUPLICATE or not author.is_person:
        return
    text = refusal_text(result.refusal, author.language, trusted=trusted)
    await send_ephemeral(bot, msg.chat.id, author.user_id, text, reply_to=msg.message_id)
