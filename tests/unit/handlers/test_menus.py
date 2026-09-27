"""Меню бота на модуле menus SDK: дерево, тексты, кнопки и их хендлеры."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from sagenza_tgbot_sdk.menus import Button, MenuContext
from sagenza_tgbot_sdk.menus.testing import crawl

from handlers import admin_handler, audio_handler, menus
from services.i18n import t


def _admin_event(text: str | None = None) -> MagicMock:
    event = MagicMock()
    event.from_user.username = "admin"
    event.from_user.language_code = "ru"
    event.message.text = text
    return event


@pytest.fixture(autouse=True)
def _admins():
    with patch("filters.dispatcher_filters.ADMINS", ["admin"]):
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["ru", "en"])
async def test_every_menu_opens_and_every_button_is_wired(locale, fake_redis):
    ctx = menus.menus.context(_admin_event(), locale=locale)

    report = await crawl(menus.menus, ctx, locales=[locale])

    report.raise_for_problems()
    assert {
        "admin@0",
        "bot@0",
        "audio_main@0",
        "audio_post@0",
        "ftp_main@0",
        "wp@0",
        "boosty@0",
        "notes_groups@0",
        "questions_groups@0",
    } <= set(report.opened)


@pytest.mark.asyncio
async def test_menus_are_hidden_from_non_admins():
    stranger = _admin_event()
    stranger.from_user.username = "stranger"

    _text, markup = await menus.menus.render(menus.menus.context(stranger), menus.AUDIO_MAIN_MENU)

    assert markup.inline_keyboard == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("type_episode", "labels"),
    [("main", {"audio_ftp", "audio_site", "audio_forward"}), ("aftershow", {"audio_ftp", "audio_boosty"})],
)
async def test_audio_menu_depends_on_episode_type(type_episode, labels):
    markup = await menus.audio_menu_markup(_admin_event(), type_episode)

    assert {b.text for row in markup.inline_keyboard for b in row} == {t(key) for key in labels}


def test_dangerous_buttons_ask_for_confirmation():
    confirm = {
        item.node_id
        for menu in menus.menus.all_menus.values()
        for item in menu.items
        if isinstance(item, Button) and item.confirm
    }
    assert confirm == {"shutdown", "restart", "forward"}


def _pressed_under(message: MagicMock) -> MenuContext:
    callback = MagicMock(spec=CallbackQuery, message=message)
    callback.from_user = MagicMock(username="admin", language_code="ru")
    return menus.menus.context(callback)


@pytest.mark.asyncio
async def test_menu_under_audio_edits_the_caption():
    message = MagicMock(spec=Message, text=None, edit_caption=AsyncMock(), edit_text=AsyncMock())

    await _pressed_under(message).put("caption", None)

    message.edit_caption.assert_awaited_once_with(caption="caption", reply_markup=None)
    message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_menu_under_text_edits_the_text():
    message = MagicMock(spec=Message, text="menu", edit_caption=AsyncMock(), edit_text=AsyncMock())

    await _pressed_under(message).put("title", None)

    message.edit_text.assert_awaited_once_with("title", reply_markup=None)
    message.edit_caption.assert_not_awaited()


@pytest.mark.asyncio
async def test_unchanged_caption_is_not_an_error():
    error = TelegramBadRequest(MagicMock(), "message is not modified")
    message = MagicMock(spec=Message, text=None, edit_caption=AsyncMock(side_effect=error))

    await _pressed_under(message).put("caption", None)


@pytest.mark.asyncio
async def test_admin_command_sends_the_panel():
    msg = MagicMock()
    with patch.object(menus.menus, "send", new=AsyncMock()) as send:
        await menus.admin(msg, username="admin", language="en")

    send.assert_awaited_once_with(msg, menus.ADMIN_MENU, language="en")


def _ctx(**data) -> MagicMock:
    ctx = MagicMock(locale="ru", menu_id=menus.AUDIO_MAIN_MENU, data=data)
    ctx.event.from_user.username = "admin"
    ctx.answer = AsyncMock()
    ctx.show = AsyncMock()
    ctx.message.audio.file_name = "0042_rz.mp3"
    ctx.message.audio.file_id = "audio"
    return ctx


@pytest.mark.asyncio
async def test_forward_sends_pins_and_restores_the_menu():
    sent = MagicMock(message_id=5, audio=MagicMock())
    bot = MagicMock(
        send_audio=AsyncMock(return_value=sent),
        pin_chat_message=AsyncMock(),
        get_chat=AsyncMock(return_value=MagicMock(pinned_message=MagicMock(message_id=5))),
    )
    ctx = _ctx(bot=bot)
    ctx.message.answer = AsyncMock()
    with (
        patch.object(audio_handler, "load_template_info", new=AsyncMock(return_value={"info": {"number": "42"}})),
        patch.object(audio_handler, "generate_podcast_text", return_value="text"),
        patch.object(audio_handler, "FORWARD_CHAT_USERNAME", "@chat"),
        patch.object(audio_handler, "Message", MagicMock),
    ):
        await audio_handler.forward_to_chat(ctx)

    bot.send_audio.assert_awaited_once_with(chat_id="@chat", audio="audio", caption="text", parse_mode="HTML")
    bot.pin_chat_message.assert_awaited_once()
    ctx.answer.assert_awaited_once_with(t("forwarded"))
    ctx.show.assert_awaited_once_with(menus.AUDIO_MAIN_MENU)


@pytest.mark.asyncio
async def test_forward_without_template_info_reports_it():
    bot = MagicMock(send_audio=AsyncMock())
    ctx = _ctx(bot=bot)
    with patch.object(audio_handler, "load_template_info", new=AsyncMock(return_value=None)):
        await audio_handler.forward_to_chat(ctx)

    bot.send_audio.assert_not_awaited()
    ctx.answer.assert_awaited_once_with(t("invalid_input"), alert=True)
    ctx.show.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "action", "text"),
    [
        (admin_handler.shutdown, "shutdown_bot", "bot_shutting_down"),
        (admin_handler.restart, "restart_bot", "bot_restarting"),
    ],
)
async def test_bot_process_buttons(handler, action, text):
    ctx = _ctx()
    with patch.object(admin_handler, action) as act:
        await handler(ctx)

    act.assert_called_once()
    ctx.answer.assert_awaited_once_with(t(text), alert=True)


@pytest.mark.asyncio
async def test_send_logs_reports_missing_archive():
    ctx = _ctx()
    with patch.object(admin_handler, "get_zip_logs", return_value=None):
        await admin_handler.send_logs(ctx)

    ctx.answer.assert_awaited_once_with(t("logs_failed"), alert=True)
