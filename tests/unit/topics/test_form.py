"""Вариант C: анкета «Предложить тему» эфемерно в группе и в личке."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, User
from dialog_engine import ValidationError

import config
from forms import topic_suggestion as form
from handlers import topics_form_handler as fh
from services.i18n import t
from services.topics import TopicSource, TopicStatus
from services.topics.runtime import topic_service

LINK = "https://t.me/test_bot?start=topic"
GROUP_ID = -1001234567890
USER = User(id=7, is_bot=False, first_name="Listener", username="listener", language_code="ru")


@pytest.fixture(autouse=True)
def _link():
    with patch.object(fh, "start_link", AsyncMock(return_value=LINK)):
        yield


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=GROUP_ID, user_id=USER.id))


def _bad_request():
    return TelegramBadRequest(method=SendMessage(chat_id=1, text="x"), message="EPHEMERAL_NOT_ALLOWED")


def _message(bot, text="", *, chat_type=ChatType.SUPERGROUP, ephemeral_id=None):
    msg = MagicMock()
    msg.bot = bot
    msg.text = text
    msg.from_user = USER
    msg.chat.type = chat_type
    msg.chat.id = GROUP_ID if chat_type != ChatType.PRIVATE else USER.id
    msg.chat.username = "test_group" if chat_type != ChatType.PRIVATE else None
    msg.ephemeral_message_id = ephemeral_id
    msg.reply = AsyncMock()
    return msg


def _callback(bot, data, *, message):
    callback = MagicMock(spec=CallbackQuery)
    callback.id = "cb-1"
    callback.bot = bot
    callback.data = data
    callback.from_user = USER
    callback.message = message
    callback.answer = AsyncMock()
    return callback


def _button(markup, text):
    return next(b for row in markup.inline_keyboard for b in row if b.text == text)


def test_form_needs_both_flags(monkeypatch):
    assert fh.form_enabled()
    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "off")
    assert not fh.form_enabled()
    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "private")
    monkeypatch.setattr(config, "TOPICS_ENABLED", False)
    assert not fh.form_enabled()


def test_validator_uses_topic_length_limits(fake_redis):
    ctx = MagicMock()
    ctx.step.id = form.TEXT
    with pytest.raises(ValidationError) as error:
        form.check_topic("а?", ctx)
    assert error.value.key == "topics_refused_too_short"
    assert form.check_topic("  про   гостей  ", ctx) == "про гостей"


def test_confirm_text_escapes_the_topic_and_expiry_has_own_text():
    text = form.resolve_text("topics_form_confirm", {form.TEXT: "<b>x</b>"}, {"lang": "ru"})
    assert "&lt;b&gt;x&lt;/b&gt;" in text
    assert form.resolve_text("de.alert.expired", {}, {}) == t("topics_form_expired")


@pytest.mark.asyncio
async def test_private_form_puts_topic_into_queue(fake_redis, bot, state):
    sent = MagicMock(message_id=11)
    sent.chat.id = USER.id
    bot.send_message = AsyncMock(return_value=sent)
    bot.edit_message_text = AsyncMock()
    metrics = MagicMock()

    await fh.start_in_private(_message(bot, "/start topic", chat_type=ChatType.PRIVATE), state, metrics)
    assert bot.send_message.await_args.kwargs["text"] == t("topics_form_ask", min=5, max=50)

    await fh.on_text(_message(bot, "  как выбирать   гостей ", chat_type=ChatType.PRIVATE), state)
    confirm = bot.edit_message_text.await_args.kwargs
    assert "как выбирать гостей" in confirm["text"]

    in_private = _message(bot, chat_type=ChatType.PRIVATE)
    in_private.message_id = 11
    press = _callback(bot, _button(confirm["reply_markup"], t("de-button-confirm")).callback_data, message=in_private)
    await fh.on_button(press, state, metrics)

    [topic] = await topic_service().repository.list(TopicStatus.NEW)
    assert (topic.text, topic.source, topic.chat_id) == ("как выбирать гостей", TopicSource.FORM, None)
    assert topic.author.user_id == USER.id
    assert bot.edit_message_text.await_args.kwargs["text"] == t("topics_form_accepted")
    metrics.event.assert_any_call("topic_form", mode="private")
    metrics.event.assert_any_call("topic_suggested", source=TopicSource.FORM)


@pytest.mark.asyncio
async def test_group_form_is_ephemeral_end_to_end(fake_redis, bot, state):
    sent = MagicMock(ephemeral_message_id=77)
    sent.chat.id = GROUP_ID
    bot.send_message = AsyncMock(return_value=sent)
    bot.edit_ephemeral_message_text = AsyncMock()

    await fh.topic_command(_message(bot, "/topic", ephemeral_id=5), state, bot)
    ask = bot.send_message.await_args.kwargs
    assert ask["ephemeral_message_parameters"].receiver_user_id == USER.id
    assert ask["reply_parameters"].ephemeral_message_id == 5
    assert ask["reply_markup"].force_reply

    await fh.on_text(_message(bot, "тема про кино", ephemeral_id=6), state)
    confirm = bot.edit_ephemeral_message_text.await_args.kwargs
    assert confirm["ephemeral_message_id"] == 77

    on_form = _message(bot, ephemeral_id=77)
    press = _callback(bot, _button(confirm["reply_markup"], t("de-button-confirm")).callback_data, message=on_form)
    await fh.on_button(press, state)

    [topic] = await topic_service().repository.list(TopicStatus.NEW)
    assert (topic.text, topic.chat_id) == ("тема про кино", GROUP_ID)
    assert bot.edit_ephemeral_message_text.await_args.kwargs["text"] == t("topics_form_accepted")


@pytest.mark.asyncio
async def test_cancel_says_so_and_saves_nothing(fake_redis, bot, state):
    sent = MagicMock(message_id=11)
    sent.chat.id = USER.id
    bot.send_message = AsyncMock(return_value=sent)
    bot.edit_message_text = AsyncMock()
    await fh.start_in_private(_message(bot, chat_type=ChatType.PRIVATE), state)
    cancel = _button(bot.send_message.await_args.kwargs["reply_markup"], t("de-button-cancel"))

    in_private = _message(bot, chat_type=ChatType.PRIVATE)
    in_private.message_id = 11
    await fh.on_button(_callback(bot, cancel.callback_data, message=in_private), state)

    assert bot.edit_message_text.await_args.kwargs["text"] == t("topics_form_cancelled")
    assert await topic_service().repository.count(TopicStatus.NEW) == 0


def test_plain_group_messages_are_not_form_answers(bot):
    assert not fh._is_answer(_message(bot, "просто болтаю"))
    assert fh._is_answer(_message(bot, "ответ", ephemeral_id=3))
    assert fh._is_answer(_message(bot, "в личке", chat_type=ChatType.PRIVATE))


@pytest.mark.asyncio
async def test_command_falls_back_to_private_link(fake_redis, bot, state):
    bot.send_message = AsyncMock(side_effect=_bad_request())
    msg = _message(bot, "/topic")
    metrics = MagicMock()

    await fh.topic_command(msg, state, bot, metrics)

    text, markup = msg.reply.await_args.args[0], msg.reply.await_args.kwargs["reply_markup"]
    assert text == t("topics_form_go_private")
    assert markup.inline_keyboard[0][0].url == LINK
    session, _ui = await form.storage.load(state)
    assert session is None
    metrics.event.assert_called_once_with("topic_form", mode="fallback")


@pytest.mark.asyncio
async def test_button_opens_ephemeral_form_or_private_link(fake_redis, bot, state, monkeypatch):
    sent = MagicMock(ephemeral_message_id=77)
    sent.chat.id = GROUP_ID
    bot.send_message = AsyncMock(return_value=sent)
    press = _callback(bot, fh.SUGGEST_CALLBACK, message=_message(bot))

    await fh.suggest_button(press, state, bot)

    assert bot.send_message.await_args.kwargs["ephemeral_message_parameters"].callback_query_id == "cb-1"
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
async def test_topic_command_is_registered_as_ephemeral(bot, monkeypatch):
    bot.set_my_commands = AsyncMock()

    await fh.register_group_commands(bot)
    [command] = bot.set_my_commands.await_args.args[0]
    assert (command.command, command.is_ephemeral) == ("topic", True)
    assert bot.set_my_commands.await_args.kwargs["scope"].chat_id == "@test_group"

    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "off")
    bot.set_my_commands.reset_mock()
    await fh.register_group_commands(bot)
    bot.set_my_commands.assert_not_awaited()
