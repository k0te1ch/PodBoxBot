"""Как слушатель сам добавляет тему или вопрос: команды и анкета.

Анкета одна на всё: в группе она эфемерная, в личке бота обычная.

* ``/topic`` в чате тем: анкета с выбором типа (тема или вопрос).
  ``/question`` там же: сразу вопрос. Команды объявлены эфемерными
  (``is_ephemeral`` в ``setMyCommands``), поэтому ни они, ни ответы бота
  группе не видны.
* Кнопка «Предложить тему или вопрос» под сообщением, которое ведущие
  публикуют в чат из ``/admin``. Нажатие даёт ``callback_query_id`` — с ним
  бот вправе прислать эфемерное сообщение даже без прав администратора.
* ``t.me/<бот>?start=topic`` — та же анкета в личке. Это запасной путь: туда
  ведёт кнопка, когда эфемерная отправка не удалась, и туда же всё идёт при
  ``TOPICS_FORM_MODE=private``.
* ``/topic`` (``/тема``) и ``/question`` (``/вопрос``) в личке бота: тип уже
  известен, анкета сразу просит текст. Латинские команды есть в меню команд
  лички, кириллические работают, если их набрать: Telegram не пускает
  кириллицу в меню команд.
* Текст сразу после команды (``/вопрос Почему небо голубое?``) добавляется без
  анкеты, и в личке, и в чате.

Админ в личке добавляет пункты теми же командами и кнопками «➕ Тема»,
«➕ Вопрос» под списком: для него нет лимита, бана и минимальной длины.
"""

import os
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
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
from dialog_engine import DialogEngine, DialogError, DialogSession
from dialog_engine.integrations.aiogram import (
    DefaultSender,
    DialogCallbackFilter,
    DialogSender,
    DialogTurn,
    EphemeralSender,
    MessageAnchor,
    StepView,
)
from loguru import logger
from sagenza_tgbot_sdk.menus import MenuContext

import config as bot_config
from forms.service_message import service_message_runner
from forms.topic_suggestion import FORMS, FULL, KIND, TEXT, TYPED, Form, kind_of
from forms.upload_file import upload_file_runner
from handlers.topics_handler import (
    QUESTION_COMMANDS,
    TOPIC_COMMANDS,
    kind_of_command,
    react,
    record_added,
    refusal_text,
)
from services.i18n import t
from services.topics import Added, Item, Kind, Source
from services.topics.delivery import send_ephemeral
from services.topics.listing import item_text
from services.topics.runtime import (
    author_from_user,
    author_of,
    count_event,
    is_admin,
    is_topics_chat,
    language_of,
    topic_list,
    topics_enabled,
)

# Диалоги админа в личке, которые тоже ждут текст.
OTHER_DIALOGS = (upload_file_runner, service_message_runner)
START_PAYLOAD = "topic"
COMMANDS = (*TOPIC_COMMANDS, *QUESTION_COMMANDS)
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


def _context(user: User | None, chat_id: int | None, kind: Kind | None, *, trusted: bool = False) -> dict[str, Any]:
    """Контекст анкеты. *trusted*: анкету открыл админ в личке, пункт пойдёт
    в список без лимита и бана. Контекст лежит в FSM бота, подделать его нельзя."""
    context: dict[str, Any] = {"lang": language_of(user), "chat_id": chat_id, "trusted": trusted}
    if kind is not None:
        context[KIND] = kind.value
    return context


async def _forget_forms(state: FSMContext) -> None:
    """Новая анкета заменяет прежнюю, какой бы та ни была."""
    for form in FORMS:
        await form.storage.clear(state)


async def start_link(bot: Bot) -> str:
    return await create_start_link(bot, START_PAYLOAD)


async def _link_markup(bot: Bot, locale: str) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(text=t("topics_form_open_private", locale), url=await start_link(bot))
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


async def _start_ephemeral(
    event: CallbackQuery | Message, state: FSMContext, chat_id: int, kind: Kind | None, metrics: Any
) -> bool:
    """Анкета эфемерно в группе; ``False``, если Telegram не дал её прислать."""
    form = FULL if kind is None else TYPED
    await _forget_forms(state)
    try:
        await form.group_runner.start(
            state, EphemeralSender.for_event(event), context=_context(event.from_user, chat_id, kind)
        )
    except (TelegramAPIError, DialogError) as error:
        logger.info(f"ephemeral topic form in {chat_id} failed, falling back to private: {error!r}")
        await form.storage.clear(state)
        count_event(metrics, "topic_form", mode="fallback")
        return False
    count_event(metrics, "topic_form", mode=EPHEMERAL)
    return True


async def start_private_form(
    bot: Bot, state: FSMContext, chat_id: int, user: User | None, kind: Kind | None, *, trusted: bool, metrics: Any
) -> None:
    """Анкета в личке; с известным типом она сразу просит текст."""
    form = FULL if kind is None else TYPED
    await _forget_forms(state)
    await form.private_runner.start(
        state, DefaultSender(bot, chat_id), context=_context(user, None, kind, trusted=trusted)
    )
    count_event(metrics, "topic_form", mode=PRIVATE)


async def _add(bot: Bot, item: Item, *, trusted: bool, metrics: Any) -> Added:
    result = await topic_list(bot).add(item, trusted=trusted)
    await record_added(result, item.kind, item.source, metrics)
    return result


def _added_text(result: Added, locale: str, *, trusted: bool) -> str:
    """Что ответить на принятый или отклонённый пункт."""
    if result.item is None:
        return refusal_text(result.refusal, locale, trusted=trusted)
    if trusted:
        return t("topics_admin_added", locale, line=item_text(result.item, locale))
    return t(f"topics_added_{result.item.kind}", locale)


router = Router(name=os.path.splitext(os.path.basename(__file__))[0])


@router.message(form_enabled, _in_topics_chat, Command(*COMMANDS, ignore_case=True))
async def group_command(msg: Message, command: CommandObject, state: FSMContext, bot: Bot, metrics: Any = None):
    """``/topic`` и ``/question`` в чате тем: текст после команды идёт в список
    сразу, без текста открывается анкета."""
    if msg.sender_chat is not None or msg.from_user is None:
        # От имени канала или анонимного админа: ответить эфемерно некому.
        return
    kind = kind_of_command(command.command)
    locale = language_of(msg.from_user)
    if command.args:
        await _add_from_group(msg, command.args, kind, bot, metrics)
        return
    # /topic без текста: анкета спросит, тема это или вопрос.
    asked = None if kind is Kind.TOPIC else kind
    if form_mode() == EPHEMERAL and await _start_ephemeral(msg, state, msg.chat.id, asked, metrics):
        return
    await msg.reply(t("topics_form_go_private", locale), reply_markup=await _link_markup(bot, locale))


async def _add_from_group(msg: Message, text: str, kind: Kind, bot: Bot, metrics: Any) -> None:
    """Пункт из команды с текстом в чате тем. Админа лимит и бан не касаются."""
    visible = msg.ephemeral_message_id is None
    trusted = is_admin(msg)
    item = Item(
        text=text,
        kind=kind,
        author=author_of(msg),
        source=Source.ADMIN if trusted else Source.FORM,
        chat_id=msg.chat.id,
        message_id=msg.message_id if visible else None,
    )
    result = await _add(bot, item, trusted=trusted, metrics=metrics)
    if result.item is not None and visible:
        await react(msg)
    if result.item is not None and not bot_config.TOPICS_ACK_EPHEMERAL:
        return
    answer = _added_text(result, item.author.language, trusted=trusted)
    await send_ephemeral(bot, msg.chat.id, msg.from_user.id, answer, reply_to=msg.message_id if visible else None)


@router.callback_query(form_enabled, F.data == SUGGEST_CALLBACK)
async def suggest_button(callback: CallbackQuery, state: FSMContext, bot: Bot, metrics: Any = None):
    message = callback.message
    in_group = form_mode() == EPHEMERAL and _in_group(message)
    if in_group and await _start_ephemeral(callback, state, message.chat.id, None, metrics):
        await callback.answer()
        return
    # Ссылки вида t.me/<бот>?start=... answerCallbackQuery открывает любому боту.
    await callback.answer(url=await start_link(bot))


def _in_private(message: Message) -> bool:
    """Личка, где анкета доступна: слушателю при включённой анкете, админу всегда."""
    return message.chat.type == ChatType.PRIVATE and (form_enabled() or is_admin(message))


@router.message(topics_enabled, _in_private, Command(*COMMANDS, ignore_case=True))
async def private_command(msg: Message, command: CommandObject, state: FSMContext, bot: Bot, metrics: Any = None):
    """``/тема`` и ``/вопрос`` в личке: с текстом пункт добавляется сразу,
    без текста анкета просит его. Админу не мешают ни лимит, ни бан."""
    kind = kind_of_command(command.command)
    trusted = is_admin(msg)
    if not command.args:
        await start_private_form(bot, state, msg.chat.id, msg.from_user, kind, trusted=trusted, metrics=metrics)
        return
    item = Item(
        text=command.args,
        kind=kind,
        author=author_from_user(msg.from_user),
        source=Source.ADMIN if trusted else Source.FORM,
    )
    result = await _add(bot, item, trusted=trusted, metrics=metrics)
    await msg.answer(_added_text(result, item.author.language, trusted=trusted))


@router.message(topics_enabled, _in_private, CommandStart(deep_link=True, magic=F.args == START_PAYLOAD))
async def start_in_private(msg: Message, state: FSMContext, bot: Bot, metrics: Any = None):
    """Анкета в личке по ссылке ``?start=topic``: с выбором типа."""
    await start_private_form(bot, state, msg.chat.id, msg.from_user, None, trusted=is_admin(msg), metrics=metrics)


def _is_answer(message: Message) -> bool:
    """Ответ анкете: в личке любой текст, кроме команды, в группе только эфемерный.

    Обычное сообщение в группе — это разговор с чатом, а не ответ боту: иначе
    брошенная анкета съела бы следующую реплику автора.
    """
    if (message.text or "").startswith("/"):
        return False
    if message.chat.type == ChatType.PRIVATE:
        return True
    return _in_topics_chat(message) and message.ephemeral_message_id is not None


def _touched(session: DialogSession, engine: DialogEngine) -> float:
    """Когда с диалогом работали последний раз: движок отсчитывает от этого срок сессии."""
    if session.expires_at is None or engine.ttl is None:
        return 0.0
    return session.expires_at - engine.ttl


async def _expects_text(form: Form, state: FSMContext) -> bool:
    """Ждёт ли анкета текст от этого человека.

    В личке у админа может одновременно идти диалог загрузки выпуска или
    сервисного сообщения, и он тоже ждёт текст. Сообщение достаётся тому
    диалогу, с которым работали последним: иначе забытая анкета съела бы
    шаблон выпуска, а незаконченная загрузка не давала бы добавить тему.
    """
    session, _ui = await form.storage.load(state)
    if session is None or not session.is_active:
        return False
    engine = form.private_runner.engine
    for rival in OTHER_DIALOGS:
        other, _ui = await rival.storage.load(state)
        if other is None or not other.is_active or rival.engine.is_expired(other):
            continue
        # Устаревшая анкета уступает живому диалогу молча, а не отвечает
        # «анкета устарела» на текст, который писали не ей.
        if engine.is_expired(session) or _touched(other, rival.engine) > _touched(session, engine):
            return False
    return True


async def on_text(form: Form, msg: Message, state: FSMContext) -> None:
    await form.runner(_in_group(msg)).on_text(msg.text or "", state, _sender(msg))


async def on_button(form: Form, callback: CallbackQuery, state: FSMContext, metrics: Any = None) -> None:
    sender = _sender(callback)
    turn = await form.runner(_in_group(callback.message)).on_callback(callback.data, state, sender)
    await callback.answer(text=turn.alert, show_alert=bool(turn.alert))
    outcome = await _outcome(turn, callback.from_user, callback.bot, metrics)
    anchor = _anchor(callback)
    if outcome is not None and anchor is not None:
        await sender.show(StepView(text=outcome), anchor)


def _register(form: Form) -> None:
    """Хендлеры ответа и кнопок для одной анкеты."""

    async def text(msg: Message, state: FSMContext):
        await on_text(form, msg, state)

    async def button(callback: CallbackQuery, state: FSMContext, metrics: Any = None):
        await on_button(form, callback, state, metrics)

    async def expects_text(_msg: Message, state: FSMContext) -> bool:
        return await _expects_text(form, state)

    # Не form_enabled: при TOPICS_FORM_MODE=off анкета закрыта слушателям, но
    # админ по-прежнему добавляет пункты через неё.
    router.message.register(text, topics_enabled, F.text, _is_answer, expects_text)
    router.callback_query.register(button, topics_enabled, DialogCallbackFilter(form.dialog_id))


for _form in FORMS:
    _register(_form)


async def _outcome(turn: DialogTurn, user: User, bot: Bot, metrics: Any) -> str | None:
    """Текст итога анкеты или ``None``, если анкета ещё идёт."""
    locale = turn.context.get("lang") or language_of(user)
    if turn.cancelled and not turn.expired:
        return t("topics_form_cancelled", locale)
    if not turn.finished:
        return None
    trusted = bool(turn.context.get("trusted"))
    item = Item(
        text=turn.answers[TEXT],
        kind=kind_of(turn.answers, turn.context),
        author=author_from_user(user),
        source=Source.ADMIN if trusted else Source.FORM,
        chat_id=turn.context.get("chat_id"),
    )
    result = await _add(bot, item, trusted=trusted, metrics=metrics)
    return _added_text(result, locale, trusted=trusted)


async def post_suggest_button(ctx: MenuContext) -> None:
    """Кнопка админ-панели: сообщение с «Предложить тему или вопрос» в чат тем."""
    bot: Bot = ctx.data["bot"]
    if form_mode() == EPHEMERAL:
        button = InlineKeyboardButton(text=t("topics_form_button"), callback_data=SUGGEST_CALLBACK)
    else:
        button = InlineKeyboardButton(text=t("topics_form_button"), url=await start_link(bot))
    try:
        await bot.send_message(
            chat_id=bot_config.TOPICS_CHAT,
            text=t("topics_form_invite"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button]]),
        )
    except TelegramAPIError as error:
        logger.error(f"topic button to {bot_config.TOPICS_CHAT} failed: {error!r}")
        await ctx.answer(ctx.text("topics_form_post_failed"), alert=True)
        return
    await ctx.answer(ctx.text("topics_form_posted", chat=bot_config.TOPICS_CHAT))


def _commands(topic_key: str, *, ephemeral: bool = False) -> list[BotCommand]:
    flag = True if ephemeral else None
    return [
        BotCommand(command=TOPIC_COMMANDS[0], description=t(topic_key), is_ephemeral=flag),
        BotCommand(command=QUESTION_COMMANDS[0], description=t("topics_form_command_question"), is_ephemeral=flag),
    ]


async def register_group_commands(bot: Bot) -> None:
    """``/topic`` и ``/question`` в меню команд чата тем; эфемерные, если анкета эфемерная.

    Эфемерную команду Telegram доставляет только боту, и ответить на неё
    можно без прав администратора.
    """
    if not form_enabled():
        return
    commands = _commands("topics_form_command", ephemeral=form_mode() == EPHEMERAL)
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=bot_config.TOPICS_CHAT))
    except TelegramAPIError as error:
        logger.warning(f"could not set topic commands for {bot_config.TOPICS_CHAT}: {error!r}")


def private_commands() -> list[BotCommand]:
    """``/topic`` и ``/question`` для меню команд лички, когда анкета включена."""
    return _commands("topics_form_command_topic") if form_enabled() else []
