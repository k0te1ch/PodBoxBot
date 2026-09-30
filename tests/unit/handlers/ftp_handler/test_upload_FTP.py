from unittest.mock import AsyncMock, MagicMock

import pytest

from config import FILES_PATH
from handlers import ftp_handler
from shared.kafka.models.upload_event import UploadEvent


def _ctx(file_name: str | None = "0042_postshow_30092026.mp3"):
    ctx = MagicMock()
    ctx.locale = "ru"
    ctx.answer = AsyncMock()
    if file_name is None:
        ctx.message.audio = None
    else:
        ctx.message.audio.file_name = file_name
    status = MagicMock()
    status.chat.id = 100
    status.message_id = 7
    ctx.message.answer = AsyncMock(return_value=status)
    return ctx


@pytest.fixture
def publish(monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(ftp_handler, "publish_request", mock)
    monkeypatch.setattr(ftp_handler, "username_of", lambda ctx: "admin")
    return mock


@pytest.mark.asyncio
async def test_sends_upload_event_with_episode_type_from_sidecar(monkeypatch, publish):
    stored = {"info": {"number": "42"}, "type_episode": "aftershow"}
    monkeypatch.setattr(ftp_handler, "load_template_info", AsyncMock(return_value=stored))
    ctx = _ctx()

    await ftp_handler.upload_FTP(ctx)

    _ctx_arg, topic, schema, event = publish.await_args.args
    assert topic == "publisher.ftp.upload"
    assert schema == "upload_event.avsc"
    assert isinstance(event, UploadEvent)
    assert event.file_name == "0042_postshow_30092026.mp3"
    assert event.path == f"{FILES_PATH}/0042_postshow_30092026.mp3"
    # The publisher routes aftershows into FTP_POSTSHOW_DIR by this field.
    assert event.type_episode == "aftershow"
    assert (event.status, event.event_type) == ("pending", "request")
    assert (event.chat_id, event.message_id) == ("100", "7")
    assert publish.await_args.kwargs["status"] is ctx.message.answer.return_value


@pytest.mark.asyncio
async def test_missing_sidecar_still_uploads_to_the_root(monkeypatch, publish):
    monkeypatch.setattr(ftp_handler, "load_template_info", AsyncMock(return_value=None))
    ctx = _ctx("0768_rz_30092026.mp3")

    await ftp_handler.upload_FTP(ctx)

    event = publish.await_args.args[3]
    assert event.type_episode is None
    assert event.file_name == "0768_rz_30092026.mp3"


@pytest.mark.asyncio
async def test_message_without_audio_is_rejected(monkeypatch, publish):
    load = AsyncMock()
    monkeypatch.setattr(ftp_handler, "load_template_info", load)
    ctx = _ctx(None)

    await ftp_handler.upload_FTP(ctx)

    publish.assert_not_awaited()
    load.assert_not_awaited()
    assert ctx.answer.await_args.kwargs == {"alert": True}
