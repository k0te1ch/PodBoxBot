"""Сервисное сообщение (/service → текст → подтверждение) и кнопки RSS-уведомления."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from config import FORWARD_CHAT_USERNAME
from handlers import rss_handler, service_handler
from services.i18n import t
from services.rss import Episode

CHAT_ID = 100


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=CHAT_ID, user_id=CHAT_ID))


@pytest.fixture
def bot() -> MagicMock:
    bot = MagicMock()
    sent = MagicMock(message_id=7)
    sent.chat.id = CHAT_ID
    bot.send_message = AsyncMock(return_value=sent)
    bot.send_audio = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.edit_message_reply_markup = AsyncMock()
    return bot


def _message(text: str) -> MagicMock:
    msg = MagicMock(text=text)
    msg.chat.id = CHAT_ID
    return msg


def _callback(data: str, text: str = "notification") -> MagicMock:
    callback = MagicMock(data=data)
    callback.message.chat.id = CHAT_ID
    callback.message.text = text
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _last_buttons(bot) -> dict[str, str]:
    # Шаг подтверждения раннер рисует правкой сообщения предыдущего шага.
    call = bot.edit_message_text.call_args or bot.send_message.call_args
    markup = call.kwargs["reply_markup"]
    return {b.text: b.callback_data for row in markup.inline_keyboard for b in row}


def _sent_to_chat(bot) -> list[str]:
    return [
        c.kwargs["text"] for c in bot.send_message.await_args_list if c.kwargs.get("chat_id") == FORWARD_CHAT_USERNAME
    ]


async def _ask_confirmation(state, bot):
    await service_handler.service_command(_message("/service"), state, bot, "ru")
    assert t("service_ask_text", "ru", chat=FORWARD_CHAT_USERNAME) in str(bot.send_message.call_args)
    await service_handler.on_text(_message("Эфир переносится на завтра"), state, bot)
    buttons = _last_buttons(bot)
    return buttons[t("de-button-confirm", "ru")], buttons[t("de-button-cancel", "ru")]


@pytest.mark.asyncio
async def test_service_message_sent_after_confirm(state, bot):
    confirm, _cancel = await _ask_confirmation(state, bot)
    callback = _callback(confirm)

    await service_handler.on_button(callback, state, bot, "ru")

    assert _sent_to_chat(bot) == ["Эфир переносится на завтра"]
    assert callback.message.edit_text.await_args.args == (t("service_sent", "ru", chat=FORWARD_CHAT_USERNAME),)


@pytest.mark.asyncio
async def test_service_message_names_the_chat_by_its_title(state, bot):
    # A private group: no username, so the id from the settings is all the admin had before.
    chat = MagicMock(username=None, photo=None)
    chat.title = "Listeners <chat>"
    bot.get_chat = AsyncMock(return_value=chat)
    title = "<b>Listeners &lt;chat&gt;</b>"

    await service_handler.service_command(_message("/service"), state, bot, "ru")
    assert bot.send_message.call_args.kwargs["text"] == t("service_ask_text", "ru", chat=title)
    await service_handler.on_text(_message("Эфир переносится на завтра"), state, bot)
    assert bot.edit_message_text.call_args.kwargs["text"] == t("service_confirm", "ru", chat=title)
    callback = _callback(_last_buttons(bot)[t("de-button-confirm", "ru")])
    await service_handler.on_button(callback, state, bot, "ru")

    assert callback.message.edit_text.await_args.args == (t("service_sent", "ru", chat=title),)
    assert callback.message.edit_text.await_args.kwargs["link_preview_options"].is_disabled is True


@pytest.mark.asyncio
async def test_service_message_cancel_sends_nothing(state, bot):
    _confirm, cancel = await _ask_confirmation(state, bot)
    callback = _callback(cancel)

    await service_handler.on_button(callback, state, bot, "ru")

    assert _sent_to_chat(bot) == []
    callback.message.edit_text.assert_awaited_once_with(t("canceled", "ru"))


@pytest.mark.asyncio
async def test_service_message_reports_send_failure(state, bot):
    confirm, _cancel = await _ask_confirmation(state, bot)
    bot.send_message.side_effect = RuntimeError("chat not found")
    callback = _callback(confirm)

    await service_handler.on_button(callback, state, bot, "ru")

    assert callback.message.edit_text.await_args.args == (t("service_failed", "ru"),)


@pytest.mark.asyncio
async def test_admin_menu_opens_service_dialog(state, bot):
    ctx = MagicMock(data={"state": state, "bot": bot}, locale="ru")
    ctx.message.chat.id = CHAT_ID
    ctx.answer = AsyncMock()

    await service_handler.open_from_menu(ctx)

    session, _ui = await service_handler.storage.load(state)
    assert session is not None


EPISODE = Episode(
    guid="g-43",
    title="Episode 43",
    link="https://example.com/43",
    description="About",
    enclosure_url="https://example.com/43.mp3",
    number="43",
    type_episode="main",
)


async def _press(action: str, bot, episode: Episode | None = EPISODE) -> MagicMock:
    callback = _callback(f"rss:{action}:{EPISODE.key}")
    with patch.object(rss_handler, "load_episode", AsyncMock(return_value=episode)):
        await rss_handler.on_rss_button(callback, bot, "ru", "admin")
    return callback


@pytest.mark.asyncio
async def test_rss_to_chat_posts_link(bot):
    callback = await _press("chat", bot)

    assert _sent_to_chat(bot) == [t("rss_chat_post", "ru", title=EPISODE.title, link=EPISODE.link)]
    text = callback.message.edit_text.await_args.args[0]
    assert text.startswith("notification")
    assert t("rss_done_chat", "ru", chat=FORWARD_CHAT_USERNAME) in text
    assert callback.message.edit_text.await_args.kwargs["reply_markup"] is None


@pytest.mark.asyncio
async def test_rss_skip_only_removes_buttons(bot):
    callback = await _press("skip", bot)

    assert _sent_to_chat(bot) == []
    assert t("rss_done_skip", "ru") in callback.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_rss_expired_notification(bot):
    callback = await _press("chat", bot, episode=None)

    callback.answer.assert_awaited_once_with(t("rss_expired", "ru"), show_alert=True)
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_rss_prepare_downloads_mp3_and_shows_audio_menu(bot, tmp_path):
    saved = AsyncMock()
    with (
        patch.object(rss_handler, "FILES_PATH", tmp_path),
        patch.object(rss_handler, "download_enclosure", AsyncMock()) as download,
        patch.object(rss_handler, "save_template_info", saved),
        patch.object(rss_handler, "audio_menu_markup", AsyncMock(return_value=None)),
    ):
        callback = await _press("prepare", bot)

    url, target = download.await_args.args
    assert url == EPISODE.enclosure_url
    assert target.parent == tmp_path
    file_name, info, type_episode = saved.await_args.args
    assert file_name == target.name
    assert info["number"] == "43"
    assert type_episode == "main"
    bot.send_audio.assert_awaited_once()
    assert t("rss_done_prepare", "ru") in callback.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_rss_prepare_download_failure(bot, tmp_path):
    with (
        patch.object(rss_handler, "FILES_PATH", tmp_path),
        patch.object(rss_handler, "download_enclosure", AsyncMock(side_effect=OSError("404"))),
    ):
        callback = await _press("prepare", bot)

    bot.send_audio.assert_not_awaited()
    assert t("rss_download_failed", "ru") in callback.message.edit_text.await_args.args[0]
