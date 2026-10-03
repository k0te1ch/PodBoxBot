"""Меню бота на модуле menus SDK: дерево, тексты, кнопки и их хендлеры."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from sagenza_tgbot_sdk.menus import Button, MenuContext
from sagenza_tgbot_sdk.menus.testing import crawl

from handlers import admin_handler, audio_handler, home_handler, menus
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


PLATFORM_FLAGS = ("BOOSTY_ENABLED", "VK_ENABLED", "PATREON_ENABLED", "SPONSR_ENABLED")


@pytest.fixture(autouse=True)
def _platforms_enabled(monkeypatch):
    """Все платные площадки включены; тесты выключения снимают флаг сами."""
    import config

    for flag in PLATFORM_FLAGS:
        monkeypatch.setattr(config, flag, True)


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["ru", "en"])
async def test_every_menu_opens_and_every_button_is_wired(locale, fake_redis):
    ctx = menus.menus.context(_admin_event(), locale=locale)

    report = await crawl(menus.menus, ctx, locales=[locale])

    report.raise_for_problems()
    assert {
        "home@0",
        "home_user@0",
        "admin@0",
        "audio_main@0",
        "audio_post@0",
        "ftp_main@0",
        "wp@0",
        "boosty@0",
        "notes_groups@0",
        "vk@0",
        "patreon@0",
        "sponsr@0",
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
    [
        ("main", {"audio_ftp", "audio_site", "audio_forward"}),
        ("aftershow", {"audio_ftp", "audio_boosty", "audio_vk", "audio_patreon", "audio_sponsr"}),
    ],
)
async def test_audio_menu_depends_on_episode_type(type_episode, labels):
    markup = await menus.audio_menu_markup(_admin_event(), type_episode)

    assert {b.text for row in markup.inline_keyboard for b in row} == {t(key) for key in labels}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "label"),
    [
        ("BOOSTY_ENABLED", "audio_boosty"),
        ("VK_ENABLED", "audio_vk"),
        ("PATREON_ENABLED", "audio_patreon"),
        ("SPONSR_ENABLED", "audio_sponsr"),
    ],
)
async def test_disabled_platform_is_hidden(monkeypatch, flag, label):
    import config

    monkeypatch.setattr(config, flag, False)

    markup = await menus.audio_menu_markup(_admin_event(), "aftershow")

    labels = {b.text for row in markup.inline_keyboard for b in row}
    assert t(label) not in labels
    assert t("audio_ftp") in labels


def test_dangerous_buttons_ask_for_confirmation():
    confirm = {
        item.node_id
        for menu in menus.menus.all_menus.values()
        for item in menu.items
        if isinstance(item, Button) and item.confirm
    }
    assert confirm == {"restart", "forward", "post_button"}


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


def _start_message(username: str) -> MagicMock:
    msg = MagicMock(spec=Message, text="/start", answer=AsyncMock())
    msg.from_user = MagicMock(username=username, language_code="ru")
    return msg


def _labels(markup) -> list[str]:
    return [b.text for row in markup.inline_keyboard for b in row]


@pytest.mark.asyncio
async def test_start_shows_the_admin_home_and_starts_nothing(fake_redis, monkeypatch):
    """/start: приветствие и меню. Выпуск начинается только кнопкой или присланным mp3."""
    import config

    monkeypatch.setattr(config, "TOPICS_ENABLED", True)
    msg = _start_message("admin")
    with patch.object(menus, "_new_episode", new=AsyncMock()) as new_episode:
        await home_handler.start(msg, language="ru")

    new_episode.assert_not_awaited()
    text, markup = msg.answer.await_args.args[0], msg.answer.await_args.kwargs["reply_markup"]
    assert text == t("home_admin")
    assert _labels(markup) == [t("home_new_episode"), t("admin_topics"), t("admin_notes"), t("home_admin_panel")]


@pytest.mark.asyncio
async def test_start_shows_a_listener_their_own_menu(fake_redis, monkeypatch):
    import config

    monkeypatch.setattr(config, "TOPICS_ENABLED", True)
    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "ephemeral")
    msg = _start_message("listener")

    await home_handler.start(msg, language="ru")

    text, markup = msg.answer.await_args.args[0], msg.answer.await_args.kwargs["reply_markup"]
    assert text == t("home_user")
    assert _labels(markup) == [t("topics_form_button"), t("home_help")]


@pytest.mark.asyncio
async def test_listener_cannot_open_the_admin_home():
    stranger = _admin_event()
    stranger.from_user.username = "stranger"

    _text, markup = await menus.menus.render(menus.menus.context(stranger), menus.HOME_MENU)

    assert markup.inline_keyboard == []


@pytest.mark.asyncio
async def test_new_episode_button_starts_the_upload_in_the_menu_message():
    ctx = _ctx(state=MagicMock(), bot=MagicMock())
    with patch("handlers.podcast_handler.start_upload", new=AsyncMock()) as start_upload:
        await menus._new_episode(ctx)

    start_upload.assert_awaited_once_with(ctx.data["state"], ctx.data["bot"], ctx.message, "ru")
    ctx.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_help_is_shown_in_place_with_a_way_back():
    message = MagicMock(spec=Message, text="menu", edit_text=AsyncMock())
    ctx = _pressed_under(message)
    ctx.callback.answer = AsyncMock()

    await menus._help(ctx)

    text, markup = message.edit_text.await_args.args[0], message.edit_text.await_args.kwargs["reply_markup"]
    assert text == t("help_text")
    assert _labels(markup) == [menus.menus.text("menu-back", "ru")]


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
    # Кнопка под файлом прошлого выпуска: бот говорит, что файл заменён, а не «ошибка при вводе».
    ctx.answer.assert_awaited_once_with(t("episode_file_gone"), alert=True)
    ctx.show.assert_awaited_once()


@pytest.mark.asyncio
async def test_restart_button():
    ctx = _ctx()
    with patch.object(admin_handler, "restart_bot") as act:
        await admin_handler.restart(ctx)

    act.assert_called_once()
    ctx.answer.assert_awaited_once_with(t("bot_restarting"), alert=True)
    # The confirmation question is replaced by the menu before the restart.
    ctx.show.assert_awaited_once_with(ctx.menu_id)


@pytest.mark.asyncio
async def test_send_logs_reports_missing_archive():
    ctx = _ctx()
    with patch.object(admin_handler, "get_zip_logs", return_value=None):
        await admin_handler.send_logs(ctx)

    ctx.answer.assert_awaited_once_with(t("logs_failed"), alert=True)
