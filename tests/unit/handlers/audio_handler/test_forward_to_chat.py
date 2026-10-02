"""Пересылка эпизода в чат: проверка отправки и закрепа, причины ошибок админу."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from handlers import audio_handler
from services.i18n import t


def _bot(pinned_id: int = 5, **overrides) -> MagicMock:
    bot = MagicMock(
        send_audio=AsyncMock(return_value=MagicMock(message_id=5, audio=MagicMock())),
        send_message=AsyncMock(),
        pin_chat_message=AsyncMock(),
        get_chat=AsyncMock(return_value=MagicMock(pinned_message=MagicMock(message_id=pinned_id))),
    )
    for name, value in overrides.items():
        setattr(bot, name, value)
    return bot


def _ctx(bot) -> MagicMock:
    ctx = MagicMock(locale="ru", menu_id="audio_main", data={"bot": bot})
    ctx.event.from_user.username = "admin"
    ctx.answer = AsyncMock()
    ctx.show = AsyncMock()
    ctx.message.audio.file_name = "0042_rz.mp3"
    ctx.message.audio.file_id = "audio"
    ctx.status = MagicMock(edit_text=AsyncMock())
    ctx.message.answer = AsyncMock(return_value=ctx.status)
    return ctx


async def _forward(ctx, text: str = "<b>Title</b>\n\nbody") -> None:
    with (
        patch.object(audio_handler, "load_template_info", new=AsyncMock(return_value={"info": {"number": "42"}})),
        patch.object(audio_handler, "generate_podcast_text", return_value=text),
        patch.object(audio_handler, "FORWARD_CHAT_USERNAME", "@chat"),
        patch.object(audio_handler, "Message", MagicMock),
    ):
        await audio_handler.forward_to_chat(ctx)


def _last_status(ctx) -> str:
    return ctx.status.edit_text.call_args.args[0]


def _bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=MagicMock(), message=message)


@pytest.mark.asyncio
async def test_success_reports_every_step():
    bot = _bot()
    ctx = _ctx(bot)
    await _forward(ctx)

    steps = [c.args[0] for c in ctx.status.edit_text.call_args_list]
    assert "закрепляю" in steps[0]
    assert steps[-1].startswith("✅")
    ctx.answer.assert_awaited_once_with(t("forwarded"))


@pytest.mark.asyncio
async def test_episode_without_chapters_is_forwarded():
    # The template of this episode had no Chapters and no Tags.
    stored = {"type_episode": "main", "info": {"number": "42", "title": "42. Title", "comment": "About"}}
    bot = _bot()
    ctx = _ctx(bot)
    with (
        patch.object(audio_handler, "load_template_info", new=AsyncMock(return_value=stored)),
        patch.object(audio_handler, "FORWARD_CHAT_USERNAME", "@chat"),
        patch.object(audio_handler, "Message", MagicMock),
    ):
        await audio_handler.forward_to_chat(ctx)

    caption = bot.send_audio.call_args.kwargs["caption"]
    assert caption.startswith("<b>42. Title</b>")
    assert "Таймлайн" not in caption
    ctx.answer.assert_awaited_once_with(t("forwarded"))


@pytest.mark.asyncio
async def test_long_text_goes_as_reply_under_short_caption():
    bot = _bot()
    ctx = _ctx(bot)
    text = "<b>Title</b>\n\n" + "x" * 1100
    await _forward(ctx, text)

    assert bot.send_audio.call_args.kwargs["caption"] == "<b>Title</b>"
    bot.send_message.assert_awaited_once()
    assert bot.send_message.call_args.kwargs["text"] == text
    assert bot.send_message.call_args.kwargs["reply_to_message_id"] == 5


@pytest.mark.asyncio
async def test_caption_within_limit_is_sent_whole():
    bot = _bot()
    ctx = _ctx(bot)
    text = "<b>" + "x" * 1000 + "</b>"
    await _forward(ctx, text)

    assert bot.send_audio.call_args.kwargs["caption"] == text
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_pin_rights_is_explained_to_admin():
    error = _bad_request("Bad Request: not enough rights to manage pinned messages in the chat")
    bot = _bot(pin_chat_message=AsyncMock(side_effect=error))
    ctx = _ctx(bot)
    await _forward(ctx)

    assert "не закреплено" in _last_status(ctx)
    assert "прав" in _last_status(ctx)
    ctx.answer.assert_awaited_once_with(t("forward_failed"), alert=True)


@pytest.mark.asyncio
async def test_bot_not_in_chat_is_explained_to_admin():
    error = TelegramForbiddenError(method=MagicMock(), message="Forbidden: bot is not a member of the channel chat")
    bot = _bot(send_audio=AsyncMock(side_effect=error))
    ctx = _ctx(bot)
    await _forward(ctx)

    assert "Добавьте бота в чат" in _last_status(ctx)
    bot.pin_chat_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_pin_that_did_not_stick_is_reported():
    bot = _bot(pinned_id=99)
    ctx = _ctx(bot)
    await _forward(ctx)

    assert "закреп не подтвердился" in _last_status(ctx)
    ctx.answer.assert_awaited_once_with(t("forward_failed"), alert=True)


@pytest.mark.asyncio
async def test_empty_post_text_is_reported_before_sending():
    bot = _bot()
    ctx = _ctx(bot)
    await _forward(ctx, text=None)

    bot.send_audio.assert_not_awaited()
    assert "текст поста" in _last_status(ctx)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Bad Request: chat not found", "не найден"),
        ("Bad Request: message caption is too long", "1024"),
        ("Bad Request: wrong file identifier/HTTP URL specified", "Загрузите эпизод заново"),
        ("Bad Request: can't parse entities: unclosed tag", "разметку"),
    ],
)
def test_telegram_errors_are_translated(message, expected):
    assert expected in audio_handler.explain_telegram_error(_bad_request(message), "Шаг")


def test_visible_length_ignores_tags_and_entities():
    assert audio_handler.visible_length('<b>a&amp;b</b> <a href="x">c</a>') == 5
