"""Варианты B и C: анкета «Предложить тему».

Анкета одна на всё: в группе она эфемерная (C), в личке бота обычная (B).
Диалог ``suggest`` из SDK не подключается, чтобы у слушателя не было двух
разных анкет.

Как начать:

* ``/topic`` в чате тем. Команда объявлена эфемерной (``is_ephemeral`` в
  ``setMyCommands``), поэтому ни она, ни ответы бота группе не видны.
* Кнопка «Предложить тему» под сообщением, которое ведущие публикуют в чат
  из ``/admin``. Нажатие даёт ``callback_query_id`` — с ним бот вправе
  прислать эфемерное сообщение даже без прав администратора.
* ``t.me/<бот>?start=topic`` — та же анкета в личке. Это запасной путь: туда
  ведёт кнопка, когда эфемерная отправка не удалась, и туда же всё идёт при
  ``TOPICS_FORM_MODE=private``.
* ``/topic`` или ``/тема`` в личке бота: та же анкета, что по ссылке.
  ``/topic`` есть в меню команд лички, ``/тема`` работает, если её набрать:
  Telegram не пускает кириллицу в меню команд.

Готовая тема попадает в ту же очередь, что и темы по хештегу.
"""

import os
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)
from aiogram.utils.deep_linking import create_start_link
from dialog_engine import DialogError
from dialog_engine.integrations.aiogram import (
    DefaultSender,
    DialogActiveFilter,
    DialogCallbackFilter,
    DialogRunner,
    DialogSender,
    DialogTurn,
    EphemeralSender,
    MessageAnchor,
    StepView,
)
from loguru import logger
from sagenza_tgbot_sdk.menus import MenuContext

import config as bot_config
from forms.topic_suggestion import DIALOG_ID, TEXT, group_runner, private_runner, storage
from handlers.topics_handler import record_suggestion, refusal_text
from services.i18n import t
from services.topics import Topic, TopicSource
from services.topics.runtime import author_from_user, count_event, is_topics_chat, topic_service, topics_enabled

START_PAYLOAD = "topic"
# Команды анкеты в личке; кириллическую Telegram в меню не пускает.
PRIVATE_COMMANDS = ("topic", "тема")
SUGGEST_CALLBACK = "topic:suggest"
GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)

EPHEMERAL = "ephemeral"
PRIVATE = "private"


def form_mode() -> str:
    return str(bot_config.TOPICS_FORM_MODE).lower()


def form_enabled(*_args: Any) -> bool:
    return topics_enabled() and form_mode() in (EPHEMERAL, PRIVATE)


def _in_group(message: Message | None) -> bool:
    return message is not None and message.chat.type in GROUP_TYPES


def _in_topics_chat(message: Message) -> bool:
    return _in_group(message) and is_topics_chat(message.chat)


def _runner(message: Message | None) -> DialogRunner:
    return group_runner if _in_group(message) else private_runner


def _sender(event: CallbackQuery | Message) -> DialogSender:
    message = event.message if isinstance(event, CallbackQuery) else event
    if _in_group(message):
        return EphemeralSender.for_event(event)
    return DefaultSender(event.bot, message.chat.id)


def _anchor(callback: CallbackQuery) -> MessageAnchor | None:
    """Сообщение анкеты, на кнопку которого нажали, — чтобы дописать в нём итог."""
    message = callback.message
    if message is None:
        return None
    ephemeral_id = getattr(message, "ephemeral_message_id", None)
    if ephemeral_id is not None:
        return MessageAnchor(message.chat.id, ephemeral_id, receiver_user_id=callback.from_user.id)
    return MessageAnchor(message.chat.id, message.message_id)


def _context(user: User | None, chat_id: int | None) -> dict[str, Any]:
    return {"lang": author_from_user(user).language if user else "ru", "chat_id": chat_id}


async def start_link(bot: Bot) -> str:
    return await create_start_link(bot, START_PAYLOAD)


async def _link_markup(bot: Bot, locale: str) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(text=t("topics_form_open_private", locale), url=await start_link(bot))
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


async def _start_ephemeral(event: CallbackQuery | Message, state: FSMContext, chat_id: int, metrics: Any) -> bool:
    """Анкета эфемерно в группе; ``False``, если Telegram не дал её прислать."""
    try:
        await group_runner.start(state, EphemeralSender.for_event(event), context=_context(event.from_user, chat_id))
    except (TelegramAPIError, DialogError) as error:
        logger.info(f"ephemeral topic form in {chat_id} failed, falling back to private: {error!r}")
        await storage.clear(state)
        count_event(metrics, "topic_form", mode="fallback")
        return False
    count_event(metrics, "topic_form", mode=EPHEMERAL)
    return True


router = Router(name=os.path.splitext(os.path.basename(__file__))[0])


@router.message(form_enabled, _in_topics_chat, Command("topic"))
async def topic_command(msg: Message, state: FSMContext, bot: Bot, metrics: Any = None):
    if form_mode() == EPHEMERAL and await _start_ephemeral(msg, state, msg.chat.id, metrics):
        return
    language = author_from_user(msg.from_user).language if msg.from_user else "ru"
    await msg.reply(t("topics_form_go_private", language), reply_markup=await _link_markup(bot, language))


@router.callback_query(form_enabled, F.data == SUGGEST_CALLBACK)
async def suggest_button(callback: CallbackQuery, state: FSMContext, bot: Bot, metrics: Any = None):
    message = callback.message
    in_group = form_mode() == EPHEMERAL and _in_group(message)
    if in_group and await _start_ephemeral(callback, state, message.chat.id, metrics):
        await callback.answer()
        return
    # Ссылки вида t.me/<бот>?start=... answerCallbackQuery открывает любому боту.
    await callback.answer(url=await start_link(bot))


@router.message(form_enabled, F.chat.type == ChatType.PRIVATE, Command(*PRIVATE_COMMANDS, ignore_case=True))
@router.message(
    form_enabled,
    F.chat.type == ChatType.PRIVATE,
    CommandStart(deep_link=True, magic=F.args == START_PAYLOAD),
)
async def start_in_private(msg: Message, state: FSMContext, metrics: Any = None):
    """Анкета в личке: по ссылке ``?start=topic`` и по ``/topic``, ``/тема``."""
    await private_runner.start(state, DefaultSender(msg.bot, msg.chat.id), context=_context(msg.from_user, None))
    count_event(metrics, "topic_form", mode=PRIVATE)


def _is_answer(message: Message) -> bool:
    """Ответ анкете: в личке любой текст, в группе только эфемерный.

    Обычное сообщение в группе — это разговор с чатом, а не ответ боту: иначе
    брошенная анкета съела бы следующую реплику автора.
    """
    if message.chat.type == ChatType.PRIVATE:
        return True
    return _in_topics_chat(message) and message.ephemeral_message_id is not None


@router.message(form_enabled, F.text, _is_answer, DialogActiveFilter(storage))
async def on_text(msg: Message, state: FSMContext):
    await _runner(msg).on_text(msg.text or "", state, _sender(msg))


@router.callback_query(form_enabled, DialogCallbackFilter(DIALOG_ID))
async def on_button(callback: CallbackQuery, state: FSMContext, metrics: Any = None):
    sender = _sender(callback)
    turn = await _runner(callback.message).on_callback(callback.data, state, sender)
    await callback.answer(text=turn.alert, show_alert=bool(turn.alert))
    outcome = await _outcome(turn, callback.from_user, callback.bot, metrics)
    anchor = _anchor(callback)
    if outcome is not None and anchor is not None:
        await sender.show(StepView(text=outcome), anchor)


async def _outcome(turn: DialogTurn, user: User, bot: Bot, metrics: Any) -> str | None:
    """Текст итога анкеты или ``None``, если анкета ещё идёт."""
    language = turn.context.get("lang") or author_from_user(user).language
    if turn.cancelled and not turn.expired:
        return t("topics_form_cancelled", language)
    if not turn.finished:
        return None
    topic = Topic(
        text=turn.answers[TEXT],
        author=author_from_user(user),
        source=TopicSource.FORM,
        chat_id=turn.context.get("chat_id"),
    )
    result = await topic_service(bot, metrics).suggest(topic)
    record_suggestion(result, TopicSource.FORM, metrics)
    if result.topic is not None:
        return t("topics_form_accepted", language)
    return refusal_text(result.refusal, language)


async def post_suggest_button(ctx: MenuContext) -> None:
    """Кнопка админ-панели: сообщение с «Предложить тему» в чат тем."""
    bot: Bot = ctx.data["bot"]
    if form_mode() == EPHEMERAL:
        button = InlineKeyboardButton(text=t("topics_form_button"), callback_data=SUGGEST_CALLBACK)
    else:
        button = InlineKeyboardButton(text=t("topics_form_button"), url=await start_link(bot))
    try:
        await bot.send_message(
            chat_id=bot_config.TOPICS_CHAT,
            text=t("topics_form_invite", hashtag=bot_config.TOPICS_HASHTAG or "тема"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button]]),
        )
    except TelegramAPIError as error:
        logger.error(f"topic button to {bot_config.TOPICS_CHAT} failed: {error!r}")
        await ctx.answer(ctx.text("topics_form_post_failed"), alert=True)
        return
    await ctx.answer(ctx.text("topics_form_posted", chat=bot_config.TOPICS_CHAT))


async def register_group_commands(bot: Bot) -> None:
    """``/topic`` в меню команд чата тем; эфемерная, если анкета эфемерная.

    Эфемерную команду Telegram доставляет только боту, и ответить на неё
    можно без прав администратора.
    """
    if not form_enabled():
        return
    command = BotCommand(
        command="topic", description=t("topics_form_command"), is_ephemeral=form_mode() == EPHEMERAL or None
    )
    try:
        await bot.set_my_commands([command], scope=BotCommandScopeChat(chat_id=bot_config.TOPICS_CHAT))
    except TelegramAPIError as error:
        logger.warning(f"could not set /topic for {bot_config.TOPICS_CHAT}: {error!r}")


def private_commands() -> list[BotCommand]:
    """``/topic`` для меню команд лички, когда анкета включена."""
    if not form_enabled():
        return []
    return [BotCommand(command=PRIVATE_COMMANDS[0], description=t("topics_form_command"))]
