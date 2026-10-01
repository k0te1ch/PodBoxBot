"""Команды и анкета «Предложить тему или вопрос»: эфемерно в группе и в личке."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, Message, User
from dialog_engine import ValidationError

import config
from forms import topic_suggestion as form
from handlers import topics_form_handler as fh
from services.i18n import t
from services.topics import Kind, Source
from services.topics.runtime import topic_list

LINK = "https://t.me/test_bot?start=topic"
GROUP_ID = -1001234567890
USER = User(id=7, is_bot=False, first_name="Listener", username="listener", language_code="ru")
ADMIN = User(id=1, is_bot=False, first_name="Host", username="admin", language_code="ru")


@pytest.fixture(autouse=True)
def _link():
    with patch.object(fh, "start_link", AsyncMock(return_value=LINK)):
        yield


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=GROUP_ID, user_id=USER.id))


@pytest.fixture
def private_bot(bot):
    """Бот, чьи сообщения в личке можно потом править: анкета дописывает итог в своё сообщение."""
    sent = MagicMock(message_id=11)
    sent.chat.id = USER.id
    bot.send_message = AsyncMock(return_value=sent)
    bot.edit_message_text = AsyncMock()
    return bot


def _bad_request():
    return TelegramBadRequest(method=SendMessage(chat_id=1, text="x"), message="EPHEMERAL_NOT_ALLOWED")


def _message(bot, text="", *, chat_type=ChatType.SUPERGROUP, ephemeral_id=None, user=USER, message_id=100):
    msg = MagicMock()
    msg.bot = bot
    msg.text = text
    msg.caption = None
    msg.from_user = user
    msg.sender_chat = None
    msg.message_id = message_id
    msg.chat.type = chat_type
    msg.chat.id = GROUP_ID if chat_type != ChatType.PRIVATE else user.id
    msg.chat.username = "test_group" if chat_type != ChatType.PRIVATE else None
    msg.ephemeral_message_id = ephemeral_id
    msg.reply = AsyncMock()
    msg.answer = AsyncMock()
    msg.react = AsyncMock()
    return msg


def _private(bot, text="", user=USER):
    return _message(bot, text, chat_type=ChatType.PRIVATE, user=user)


def _command(name: str, args: str | None = None) -> CommandObject:
    return CommandObject(prefix="/", command=name, args=args)


def _callback(bot, data, *, message, user=USER):
    callback = MagicMock(spec=CallbackQuery)
    callback.id = "cb-1"
    callback.bot = bot
    callback.data = data
    callback.from_user = user
    callback.message = message
    callback.answer = AsyncMock()
    return callback


def _button(markup, text):
    return next(b for row in markup.inline_keyboard for b in row if b.text == text)


def _form_message(bot, user=USER):
    on_form = _private(bot, user=user)
    on_form.message_id = 11
    return on_form


async def _press(bot, state, form_, markup, label, metrics=None, user=USER):
    press = _callback(bot, _button(markup, label).callback_data, message=_form_message(bot, user), user=user)
    await fh.on_button(form_, press, state, metrics)
    return press


async def _items():
    return await topic_list().repository.items()


def test_form_needs_both_flags(monkeypatch):
    assert fh.form_enabled()
    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "off")
    assert not fh.form_enabled()
    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "private")
    monkeypatch.setattr(config, "TOPICS_ENABLED", False)
    assert not fh.form_enabled()


def test_validator_uses_list_length_limits(fake_redis):
    ctx = MagicMock(context={})
    ctx.step.id = form.TEXT
    with pytest.raises(ValidationError) as error:
        form.check_text("а?", ctx)
    assert error.value.key == "topics_refused_too_short"
    assert form.check_text("  про   гостей  ", ctx) == "про гостей"
    # Админу короткий текст можно.
    ctx.context = {"trusted": True}
    assert form.check_text("а?", ctx) == "а?"


def test_form_texts_follow_the_kind():
    question = {"lang": "ru", form.KIND: "question"}
    assert form.resolve_text("topics_form_ask", {}, question) == t("topics_form_ask_question", min=5, max=50)
    assert form.resolve_text("topics_form_ask", {}, {"lang": "ru"}) == t("topics_form_ask_topic", min=5, max=50)
    # Тип, выбранный в анкете, важнее контекста.
    confirm = form.resolve_text("topics_form_confirm", {form.KIND: "topic", form.TEXT: "<b>x</b>"}, question)
    assert "ТЕМА - &lt;b&gt;x&lt;/b&gt;" in confirm
    assert form.resolve_text("de.alert.expired", {}, {}) == t("topics_form_expired")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "kind", "ask"),
    [
        ("вопрос", Kind.QUESTION, "topics_form_ask_question"),
        ("question", Kind.QUESTION, "topics_form_ask_question"),
        ("тема", Kind.TOPIC, "topics_form_ask_topic"),
        ("topic", Kind.TOPIC, "topics_form_ask_topic"),
    ],
)
async def test_private_command_asks_for_text_and_adds_the_item(fake_redis, private_bot, state, command, kind, ask):
    bot = private_bot
    metrics = MagicMock()

    await fh.private_command(_private(bot, f"/{command}"), _command(command), state, bot, metrics)
    assert bot.send_message.await_args.kwargs["text"] == t(ask, min=5, max=50)

    await fh.on_text(form.TYPED, _private(bot, "  как выбирать   гостей "), state)
    confirm = bot.edit_message_text.await_args.kwargs
    assert f"{t(f'topics_kind_{kind}')} - как выбирать гостей" in confirm["text"]

    await _press(bot, state, form.TYPED, confirm["reply_markup"], t("de-button-confirm"), metrics)

    [item] = await _items()
    assert (item.text, item.kind, item.source, item.chat_id) == ("как выбирать гостей", kind, Source.FORM, None)
    assert item.author.user_id == USER.id
    assert bot.edit_message_text.await_args.kwargs["text"] == t(f"topics_added_{kind}")
    metrics.event.assert_any_call("topic_form", mode="private")
    metrics.event.assert_any_call("topic_added", kind=kind.value, source="form")


@pytest.mark.asyncio
async def test_text_after_the_private_command_is_added_at_once(fake_redis, bot, state):
    msg = _private(bot, "/вопрос Почему небо голубое?")

    await fh.private_command(msg, _command("вопрос", "Почему небо голубое?"), state, bot)

    [item] = await _items()
    assert (item.kind, item.text, item.source) == (Kind.QUESTION, "Почему небо голубое?", Source.FORM)
    msg.answer.assert_awaited_once_with(t("topics_added_question"))
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_listener_is_limited_and_admin_is_not(fake_redis, bot, state):
    for index in range(2):
        await fh.private_command(_private(bot), _command("тема", f"идея номер {index}"), state, bot)
    over = _private(bot)
    await fh.private_command(over, _command("тема", "третья идея за сутки"), state, bot)
    over.answer.assert_awaited_once_with(t("topics_refused_limit", limit=2))

    by_admin = _private(bot, user=ADMIN)
    for text in ("Юг", "Как съездили в отпуск", "Что с погодой"):
        await fh.private_command(by_admin, _command("тема", text), state, bot)

    items = await _items()
    assert [item.source for item in items] == [Source.FORM] * 2 + [Source.ADMIN] * 3
    assert "5) ТЕМА - Что с погодой" in by_admin.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_banned_listener_is_refused_in_private(fake_redis, bot, state):
    await topic_list().repository.ban(USER.id, "@listener")
    msg = _private(bot)

    await fh.private_command(msg, _command("вопрос", "а можно мне спросить?"), state, bot)

    msg.answer.assert_awaited_once_with(t("topics_refused_banned"))
    assert await _items() == []


@pytest.mark.asyncio
async def test_admin_form_in_private_is_trusted(fake_redis, private_bot, state):
    bot = private_bot
    await topic_list().repository.ban(ADMIN.id, "@admin")

    await fh.start_private_form(bot, state, ADMIN.id, ADMIN, Kind.QUESTION, trusted=True, metrics=None)
    assert bot.send_message.await_args.kwargs["text"] == t("topics_form_ask_question", min=1, max=50)
    await fh.on_text(form.TYPED, _private(bot, "Юг?", user=ADMIN), state)
    confirm = bot.edit_message_text.await_args.kwargs
    await _press(bot, state, form.TYPED, confirm["reply_markup"], t("de-button-confirm"), user=ADMIN)

    [item] = await _items()
    assert (item.text, item.kind, item.source) == ("Юг?", Kind.QUESTION, Source.ADMIN)
    assert "1) ВОПРОС - Юг?" in bot.edit_message_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_deep_link_form_asks_for_the_kind_first(fake_redis, private_bot, state):
    bot = private_bot

    await fh.start_in_private(_private(bot, "/start topic"), state, bot)
    ask_kind = bot.send_message.await_args.kwargs
    assert ask_kind["text"] == t("topics_form_kind")

    await _press(bot, state, form.FULL, ask_kind["reply_markup"], t("topics_form_kind_question"))
    assert bot.edit_message_text.await_args.kwargs["text"] == t("topics_form_ask_question", min=5, max=50)

    await fh.on_text(form.FULL, _private(bot, "почему птицы летают?"), state)
    confirm = bot.edit_message_text.await_args.kwargs
    assert "ВОПРОС - почему птицы летают?" in confirm["text"]
    await _press(bot, state, form.FULL, confirm["reply_markup"], t("de-button-confirm"))

    [item] = await _items()
    assert (item.kind, item.text) == (Kind.QUESTION, "почему птицы летают?")


@pytest.mark.asyncio
async def test_group_form_is_ephemeral_end_to_end(fake_redis, bot, state):
    sent = MagicMock(ephemeral_message_id=77)
    sent.chat.id = GROUP_ID
    bot.send_message = AsyncMock(return_value=sent)
    bot.edit_ephemeral_message_text = AsyncMock()

    await fh.group_command(_message(bot, "/topic", ephemeral_id=5), _command("topic"), state, bot)
    ask_kind = bot.send_message.await_args.kwargs
    assert ask_kind["text"] == t("topics_form_kind")
    assert ask_kind["ephemeral_message_parameters"].receiver_user_id == USER.id
    assert ask_kind["reply_parameters"].ephemeral_message_id == 5
    assert ask_kind["reply_markup"].force_reply

    on_form = _message(bot, ephemeral_id=77)
    pick = _button(ask_kind["reply_markup"], t("topics_form_kind_topic"))
    await fh.on_button(form.FULL, _callback(bot, pick.callback_data, message=on_form), state)
    assert bot.edit_ephemeral_message_text.await_args.kwargs["text"] == t("topics_form_ask_topic", min=5, max=50)

    await fh.on_text(form.FULL, _message(bot, "тема про кино", ephemeral_id=6), state)
    confirm = bot.edit_ephemeral_message_text.await_args.kwargs
    assert confirm["ephemeral_message_id"] == 77

    send = _button(confirm["reply_markup"], t("de-button-confirm"))
    await fh.on_button(form.FULL, _callback(bot, send.callback_data, message=on_form), state)

    [item] = await _items()
    assert (item.text, item.kind, item.source, item.chat_id) == ("тема про кино", Kind.TOPIC, Source.FORM, GROUP_ID)
    assert bot.edit_ephemeral_message_text.await_args.kwargs["text"] == t("topics_added_topic")


@pytest.mark.asyncio
async def test_question_command_in_group_skips_the_kind_step(fake_redis, bot, state):
    sent = MagicMock(ephemeral_message_id=77)
    sent.chat.id = GROUP_ID
    bot.send_message = AsyncMock(return_value=sent)

    await fh.group_command(_message(bot, "/question", ephemeral_id=5), _command("question"), state, bot)

    assert bot.send_message.await_args.kwargs["text"] == t("topics_form_ask_question", min=5, max=50)


@pytest.mark.asyncio
async def test_text_after_the_group_command_is_added_at_once(fake_redis, bot, state):
    msg = _message(bot, "/вопрос Почему небо голубое?")
    metrics = MagicMock()

    await fh.group_command(msg, _command("вопрос", "Почему небо голубое?"), state, bot, metrics)

    [item] = await _items()
    assert (item.kind, item.text, item.source) == (Kind.QUESTION, "Почему небо голубое?", Source.FORM)
    assert (item.message_id, item.link) == (100, "https://t.me/test_group/100")
    msg.react.assert_awaited_once()
    note = bot.send_message.await_args.kwargs
    assert note["text"] == t("topics_added_question")
    assert note["ephemeral_message_parameters"].receiver_user_id == USER.id
    metrics.event.assert_called_once_with("topic_added", kind="question", source="form")


@pytest.mark.asyncio
async def test_ephemeral_group_command_with_text_has_no_message_to_react_to(fake_redis, bot, state):
    msg = _message(bot, "/тема про отпуск на море", ephemeral_id=5)

    await fh.group_command(msg, _command("тема", "про отпуск на море"), state, bot)

    [item] = await _items()
    assert (item.message_id, item.link) == (None, None)
    msg.react.assert_not_awaited()
    assert bot.send_message.await_args.kwargs["reply_parameters"] is None


@pytest.mark.asyncio
async def test_group_command_from_a_channel_is_ignored(fake_redis, bot, state):
    msg = _message(bot, "/topic")
    msg.from_user = None

    await fh.group_command(msg, _command("topic"), state, bot)

    bot.send_message.assert_not_awaited()
    msg.reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_form_replaces_the_unfinished_one(fake_redis, private_bot, state):
    bot = private_bot
    await fh.start_in_private(_private(bot, "/start topic"), state, bot)

    await fh.private_command(_private(bot, "/вопрос"), _command("вопрос"), state, bot)

    full, _ui = await form.FULL.storage.load(state)
    typed, _ui = await form.TYPED.storage.load(state)
    assert full is None and typed is not None


@pytest.mark.asyncio
async def test_cancel_says_so_and_saves_nothing(fake_redis, private_bot, state):
    bot = private_bot
    await fh.private_command(_private(bot, "/тема"), _command("тема"), state, bot)

    await _press(bot, state, form.TYPED, bot.send_message.await_args.kwargs["reply_markup"], t("de-button-cancel"))

    assert bot.edit_message_text.await_args.kwargs["text"] == t("topics_form_cancelled")
    assert await _items() == []


def test_plain_group_messages_and_commands_are_not_form_answers(bot):
    assert not fh._is_answer(_message(bot, "просто болтаю"))
    assert fh._is_answer(_message(bot, "ответ", ephemeral_id=3))
    assert fh._is_answer(_private(bot, "в личке"))
    assert not fh._is_answer(_private(bot, "/start"))


@pytest.mark.asyncio
async def test_command_falls_back_to_private_link(fake_redis, bot, state):
    bot.send_message = AsyncMock(side_effect=_bad_request())
    msg = _message(bot, "/topic")
    metrics = MagicMock()

    await fh.group_command(msg, _command("topic"), state, bot, metrics)

    text, markup = msg.reply.await_args.args[0], msg.reply.await_args.kwargs["reply_markup"]
    assert text == t("topics_form_go_private")
    assert markup.inline_keyboard[0][0].url == LINK
    session, _ui = await form.FULL.storage.load(state)
    assert session is None
    metrics.event.assert_called_once_with("topic_form", mode="fallback")


@pytest.mark.asyncio
async def test_button_opens_ephemeral_form_or_private_link(fake_redis, bot, state, monkeypatch):
    sent = MagicMock(ephemeral_message_id=77)
    sent.chat.id = GROUP_ID
    bot.send_message = AsyncMock(return_value=sent)
    press = _callback(bot, fh.SUGGEST_CALLBACK, message=_message(bot))

    await fh.suggest_button(press, state, bot)

    ask_kind = bot.send_message.await_args.kwargs
    assert ask_kind["ephemeral_message_parameters"].callback_query_id == "cb-1"
    assert ask_kind["text"] == t("topics_form_kind")
    press.answer.assert_awaited_once_with()

    bot.send_message.side_effect = _bad_request()
    press = _callback(bot, fh.SUGGEST_CALLBACK, message=_message(bot))
    await fh.suggest_button(press, state, bot)
    press.answer.assert_awaited_once_with(url=LINK)

    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "private")
    press = _callback(bot, fh.SUGGEST_CALLBACK, message=_message(bot))
    await fh.suggest_button(press, state, bot)
    press.answer.assert_awaited_once_with(url=LINK)


@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "has_callback"), [("ephemeral", True), ("private", False)])
async def test_admin_posts_the_button_to_the_chat(bot, monkeypatch, mode, has_callback):
    monkeypatch.setattr(config, "TOPICS_FORM_MODE", mode)
    ctx = MagicMock(data={"bot": bot}, answer=AsyncMock(), text=lambda key, **kw: t(key, **kw))

    await fh.post_suggest_button(ctx)

    kwargs = bot.send_message.await_args.kwargs
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert kwargs["chat_id"] == "@test_group"
    assert kwargs["text"] == t("topics_form_invite")
    assert (button.callback_data == fh.SUGGEST_CALLBACK) is has_callback
    assert (button.url == LINK) is not has_callback
    ctx.answer.assert_awaited_once_with(t("topics_form_posted", chat="@test_group"))


@pytest.mark.asyncio
async def test_failed_post_is_reported_to_admin(bot):
    bot.send_message.side_effect = _bad_request()
    ctx = MagicMock(data={"bot": bot}, answer=AsyncMock(), text=lambda key, **kw: t(key, **kw))

    await fh.post_suggest_button(ctx)

    ctx.answer.assert_awaited_once_with(t("topics_form_post_failed"), alert=True)


@pytest.mark.asyncio
async def test_group_commands_are_registered_as_ephemeral(bot, monkeypatch):
    bot.set_my_commands = AsyncMock()

    await fh.register_group_commands(bot)
    commands = bot.set_my_commands.await_args.args[0]
    assert [(command.command, command.is_ephemeral) for command in commands] == [("topic", True), ("question", True)]
    assert bot.set_my_commands.await_args.kwargs["scope"].chat_id == "@test_group"

    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "off")
    bot.set_my_commands.reset_mock()
    await fh.register_group_commands(bot)
    bot.set_my_commands.assert_not_awaited()


def test_commands_are_in_private_menu_only_when_form_is_on(monkeypatch):
    assert [(c.command, c.is_ephemeral) for c in fh.private_commands()] == [("topic", None), ("question", None)]
    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "off")
    assert fh.private_commands() == []


def _real_message(text: str, chat_type: str = "private") -> Message:
    chat_id = USER.id if chat_type == "private" else GROUP_ID
    chat = Chat(id=chat_id, type=chat_type, username=None if chat_type == "private" else "test_group")
    return Message(message_id=1, date=datetime.now(), chat=chat, from_user=USER, text=text)


async def _handled_by(handler, text: str, bot, chat_type: str = "private") -> bool:
    handlers = [h for h in fh.router.message.handlers if h.callback is handler]
    return any([(await h.check(_real_message(text, chat_type), bot=bot))[0] for h in handlers])


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["/topic", "/тема", "/Тема", "/question", "/вопрос", "/вопрос почему?"])
async def test_private_commands_are_routed(bot, text):
    assert await _handled_by(fh.private_command, text, bot)
    assert not await _handled_by(fh.group_command, text, bot)


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["/topic", "/вопрос почему небо голубое?"])
async def test_group_commands_are_routed(bot, text):
    assert await _handled_by(fh.group_command, text, bot, "supergroup")
    assert not await _handled_by(fh.private_command, text, bot, "supergroup")


@pytest.mark.asyncio
async def test_deep_link_is_routed_only_with_its_payload(bot):
    assert await _handled_by(fh.start_in_private, "/start topic", bot)
    assert not await _handled_by(fh.start_in_private, "/start other", bot)
    assert not await _handled_by(fh.start_in_private, "/start", bot)


# --- анкета и диалог загрузки выпуска в одной личке ---------------------------------


async def _start_upload(bot, state, monkeypatch, at: float) -> None:
    from dialog_engine.integrations.aiogram import DefaultSender

    from forms.upload_file import upload_file_runner

    monkeypatch.setattr(upload_file_runner.engine, "_clock", lambda: at)
    await upload_file_runner.start(state, DefaultSender(bot, ADMIN.id), context={"lang": "ru"})


async def _start_form(bot, state, monkeypatch, at: float) -> None:
    monkeypatch.setattr(form.TYPED.private_runner.engine, "_clock", lambda: at)
    await fh.start_private_form(bot, state, ADMIN.id, ADMIN, Kind.TOPIC, trusted=True, metrics=None)


@pytest.mark.asyncio
async def test_form_expects_text_only_while_it_is_open(fake_redis, private_bot, state, monkeypatch):
    assert not await fh._expects_text(form.TYPED, state)

    await _start_form(private_bot, state, monkeypatch, at=1000.0)

    assert await fh._expects_text(form.TYPED, state)
    assert not await fh._expects_text(form.FULL, state)


@pytest.mark.asyncio
async def test_unfinished_upload_does_not_block_a_form_opened_later(fake_redis, private_bot, state, monkeypatch):
    await _start_upload(private_bot, state, monkeypatch, at=1000.0)
    await _start_form(private_bot, state, monkeypatch, at=2000.0)

    assert await fh._expects_text(form.TYPED, state)


@pytest.mark.asyncio
async def test_forgotten_form_does_not_eat_the_text_of_an_upload_started_later(
    fake_redis, private_bot, state, monkeypatch
):
    await _start_form(private_bot, state, monkeypatch, at=1000.0)
    await _start_upload(private_bot, state, monkeypatch, at=2000.0)

    assert not await fh._expects_text(form.TYPED, state)


@pytest.mark.asyncio
async def test_expired_upload_does_not_block_the_form(fake_redis, private_bot, state, monkeypatch):
    from forms.upload_file import upload_file_runner

    await _start_form(private_bot, state, monkeypatch, at=1000.0)
    await _start_upload(private_bot, state, monkeypatch, at=2000.0)
    monkeypatch.setattr(upload_file_runner.engine, "_clock", lambda: 2000.0 + upload_file_runner.engine.ttl + 1)

    assert await fh._expects_text(form.TYPED, state)
