"""Карточка чата: название, ссылка и фото вместо числового id."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from fakeredis import FakeAsyncRedis

from utils import chat_card
from utils.chat_card import CardMessage, CardSender, ChatCard

PUBLIC = ChatCard("@show_chat", title="Show & chat", username="show_chat", photo_id="small", photo_key="u1")
PRIVATE = ChatCard("-1001234567890", title="Hosts <room>", photo_id="small", photo_key="u1")
UNKNOWN = ChatCard("-1001234567890")


def _chat(title="Show & chat", username="show_chat", photo=True) -> MagicMock:
    chat = MagicMock()
    chat.title = title
    chat.username = username
    chat.photo = MagicMock(small_file_id="small", small_file_unique_id="u1") if photo else None
    return chat


@pytest.fixture
def cache(monkeypatch) -> FakeAsyncRedis:
    fake = FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(chat_card, "redis", fake)
    return fake


def test_public_chat_is_a_link_with_a_small_preview_card():
    assert PUBLIC.html == '<a href="https://t.me/show_chat">Show &amp; chat</a>'
    assert PUBLIC.quoted == "«Show & chat»"
    preview = PUBLIC.preview
    assert preview.url == "https://t.me/show_chat"
    assert preview.prefer_small_media is True
    assert preview.show_above_text is False


def test_private_chat_is_a_bold_title_without_any_link():
    assert PRIVATE.html == "<b>Hosts &lt;room&gt;</b>"
    assert PRIVATE.link is None
    assert PRIVATE.preview.is_disabled is True


def test_unreadable_chat_is_shown_as_configured():
    assert (UNKNOWN.html, UNKNOWN.quoted, UNKNOWN.name) == ("-1001234567890",) * 3
    assert UNKNOWN.preview.is_disabled is True


@pytest.mark.asyncio
async def test_resolve_reads_the_chat_once_and_caches_it(cache):
    bot = MagicMock(get_chat=AsyncMock(return_value=_chat()))

    first = await chat_card.resolve(bot, "@show_chat")
    second = await chat_card.resolve(bot, "@show_chat")

    assert first == second == PUBLIC
    bot.get_chat.assert_awaited_once_with("@show_chat")
    assert 0 < await cache.ttl("chat:card:@show_chat") <= chat_card.CARD_TTL


@pytest.mark.asyncio
async def test_resolve_of_a_private_group_by_numeric_id(cache):
    bot = MagicMock(get_chat=AsyncMock(return_value=_chat(title="Hosts <room>", username=None, photo=False)))

    card = await chat_card.resolve(bot, -1001234567890)

    assert card == ChatCard("-1001234567890", title="Hosts <room>")


@pytest.mark.asyncio
async def test_resolve_falls_back_to_the_setting_and_does_not_cache_the_failure(cache):
    error = TelegramBadRequest(method=MagicMock(), message="Bad Request: chat not found")
    bot = MagicMock(get_chat=AsyncMock(side_effect=error))

    assert await chat_card.resolve(bot, "-1001234567890") == UNKNOWN
    assert await cache.keys("chat:card:*") == []


@pytest.mark.asyncio
async def test_resolve_works_without_redis():
    bot = MagicMock(get_chat=AsyncMock(return_value=_chat()))

    assert await chat_card.resolve(bot, "@show_chat") == PUBLIC


@pytest.mark.asyncio
async def test_public_chat_status_goes_as_text_with_the_preview_card(cache):
    bot = MagicMock()
    to = MagicMock(answer=AsyncMock(), answer_photo=AsyncMock())

    status = await chat_card.send(bot, to, PUBLIC, "text")
    await status.edit("done")

    to.answer_photo.assert_not_awaited()
    assert to.answer.await_args.kwargs["link_preview_options"] == PUBLIC.preview
    edit = to.answer.return_value.edit_text
    assert edit.await_args.args == ("done",)
    assert edit.await_args.kwargs["link_preview_options"] == PUBLIC.preview


@pytest.mark.asyncio
async def test_private_group_status_goes_as_its_photo_with_a_caption(cache, monkeypatch):
    monkeypatch.setattr(chat_card, "LOCAL", False)
    bot = MagicMock(
        get_file=AsyncMock(return_value=MagicMock(file_path="photos/file_1.jpg")),
        download_file=AsyncMock(return_value=BytesIO(b"jpeg")),
    )
    sent = MagicMock(photo=[MagicMock(file_id="small-sent"), MagicMock(file_id="sent")], edit_caption=AsyncMock())
    to = MagicMock(answer=AsyncMock(), answer_photo=AsyncMock(return_value=sent))

    status = await chat_card.send(bot, to, PRIVATE, "text")
    await status.edit("done")

    photo = to.answer_photo.await_args.args[0]
    assert photo.data == b"jpeg"
    assert to.answer_photo.await_args.kwargs["caption"] == "text"
    to.answer.assert_not_awaited()
    assert sent.edit_caption.await_args.kwargs["caption"] == "done"
    # The uploaded photo is reused by its file_id while the chat keeps it.
    assert await cache.get("chat:photo:u1") == "sent"
    await chat_card.send(bot, to, PRIVATE, "again")
    assert to.answer_photo.await_args.args[0] == "sent"
    bot.get_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_bot_api_photo_is_read_from_the_shared_volume(cache, monkeypatch, tmp_path):
    path = tmp_path / "file_1.jpg"
    path.write_bytes(b"local jpeg")
    monkeypatch.setattr(chat_card, "LOCAL", True)
    bot = MagicMock(get_file=AsyncMock(return_value=MagicMock(file_path=str(path))), download_file=AsyncMock())
    to = MagicMock(answer=AsyncMock(), answer_photo=AsyncMock())

    await chat_card.send(bot, to, PRIVATE, "text")

    assert to.answer_photo.await_args.args[0].data == b"local jpeg"
    bot.download_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_photo_falls_back_to_plain_text(cache):
    bot = MagicMock(get_file=AsyncMock(side_effect=TelegramBadRequest(method=MagicMock(), message="no file")))
    to = MagicMock(answer=AsyncMock(), answer_photo=AsyncMock())

    status = await chat_card.send(bot, to, PRIVATE, "text")

    to.answer_photo.assert_not_awaited()
    to.answer.assert_awaited_once()
    assert isinstance(status, CardMessage) and not status.with_photo


@pytest.mark.asyncio
async def test_private_group_without_a_photo_is_plain_text(cache):
    bot = MagicMock(get_file=AsyncMock())
    to = MagicMock(answer=AsyncMock(), answer_photo=AsyncMock())

    await chat_card.send(bot, to, ChatCard("-100", title="Hosts"), "text")

    bot.get_file.assert_not_awaited()
    assert to.answer.await_args.kwargs["link_preview_options"].is_disabled is True


@pytest.mark.asyncio
async def test_dialog_steps_carry_the_card_under_the_text():
    sent = MagicMock(message_id=7)
    sent.chat.id = 100
    bot = MagicMock(send_message=AsyncMock(return_value=sent), edit_message_text=AsyncMock())
    sender = CardSender(bot, 100, PUBLIC)

    anchor = await sender._send("step", None)
    await sender._edit(anchor, "next step", None)

    assert bot.send_message.await_args.kwargs["link_preview_options"] == PUBLIC.preview
    assert (anchor.chat_id, anchor.message_id) == (100, 7)
    assert bot.edit_message_text.await_args.kwargs["link_preview_options"] == PUBLIC.preview
