from unittest.mock import AsyncMock, MagicMock

import pytest

from config import FILES_PATH
from handlers import boosty_handler
from shared.kafka.models.boosty_event import BoostyEvent


def _ctx():
    ctx = MagicMock()
    ctx.locale = "ru"
    ctx.answer = AsyncMock()
    ctx.message.audio.file_name = "0042_postshow_30092026.mp3"
    status = MagicMock()
    status.chat.id = 100
    status.message_id = 7
    ctx.message.answer = AsyncMock(return_value=status)
    return ctx


@pytest.fixture
def publish(monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(boosty_handler, "publish_request", mock)
    monkeypatch.setattr(boosty_handler, "username_of", lambda ctx: "admin")
    return mock


@pytest.mark.asyncio
async def test_sends_aftershow_event_with_file_path(monkeypatch, publish):
    info = {"number": "42", "title": "42. Послешоу", "comment": "Описание", "chapters": [["00:00", "Начало"]]}
    monkeypatch.setattr(boosty_handler, "load_template_info", AsyncMock(return_value={"info": info}))
    ctx = _ctx()

    await boosty_handler.upload_Boosty(ctx)

    _ctx_arg, topic, schema, event = publish.await_args.args
    assert topic == "publisher.boosty.upload"
    assert schema == "boosty_event.avsc"
    assert isinstance(event, BoostyEvent)
    assert event.type_episode == "aftershow"
    assert event.path == f"{FILES_PATH}/0042_postshow_30092026.mp3"
    assert event.chapters == [["00:00", "Начало"]]
    assert event.tags == []
    assert (event.chat_id, event.message_id) == ("100", "7")


@pytest.mark.asyncio
async def test_aftershow_without_chapters_or_tags_is_accepted(monkeypatch, publish):
    info = {"number": "42", "title": "42. Послешоу", "comment": "Описание"}
    monkeypatch.setattr(boosty_handler, "load_template_info", AsyncMock(return_value={"info": info}))

    await boosty_handler.upload_Boosty(_ctx())

    event = publish.await_args.args[3]
    assert (event.chapters, event.tags) == ([], [])


@pytest.mark.asyncio
async def test_missing_sidecar_is_reported_without_publishing(monkeypatch, publish):
    monkeypatch.setattr(boosty_handler, "load_template_info", AsyncMock(return_value=None))
    ctx = _ctx()

    await boosty_handler.upload_Boosty(ctx)

    publish.assert_not_awaited()
    assert ctx.answer.await_args.kwargs == {"alert": True}
