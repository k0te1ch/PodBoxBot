from unittest.mock import AsyncMock, MagicMock

import pytest

from handlers import wordpress_handler
from services.i18n import t
from shared.kafka.models.wordpress_event import WordPressEvent

INFO = {
    "number": "768",
    "title": "768. Эпизод",
    "comment": "Описание",
    "chapters": [["00:00:00", "Начало"]],
    "tags": ["тег"],
    "recording_date": "2026-09-28",
}


def _ctx():
    ctx = MagicMock()
    ctx.locale = "ru"
    ctx.answer = AsyncMock()
    ctx.message.audio.file_name = "0768_rz_30092026.mp3"
    ctx.message.audio.duration = 3725
    status = MagicMock()
    status.chat.id = 100
    status.message_id = 7
    ctx.message.answer = AsyncMock(return_value=status)
    return ctx


@pytest.fixture
def publish(monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(wordpress_handler, "publish_request", mock)
    monkeypatch.setattr(wordpress_handler, "username_of", lambda ctx: "admin")
    return mock


@pytest.mark.asyncio
async def test_sends_wordpress_event_built_from_sidecar_and_audio(monkeypatch, publish):
    stored = {"info": dict(INFO), "type_episode": "main"}
    monkeypatch.setattr(wordpress_handler, "load_template_info", AsyncMock(return_value=stored))
    ctx = _ctx()

    await wordpress_handler.upload_WP(ctx)

    _ctx_arg, topic, schema, event = publish.await_args.args
    assert topic == "publisher.wordpress.upload"
    assert schema == "wordpress_event.avsc"
    assert isinstance(event, WordPressEvent)
    # Podlove finds the media file by this slug.
    assert event.slug == "0768_rz_30092026"
    assert event.duration == 3725
    assert event.recording_date == "2026-09-28"
    assert (event.number, event.title, event.comment) == ("768", "768. Эпизод", "Описание")
    assert event.chapters == [["00:00:00", "Начало"]]
    assert event.tags == ["тег"]
    assert event.type_episode == "main"
    assert (event.chat_id, event.message_id) == ("100", "7")


@pytest.mark.asyncio
async def test_missing_sidecar_is_reported_without_publishing(monkeypatch, publish, publish_board_stub):
    monkeypatch.setattr(wordpress_handler, "load_template_info", AsyncMock(return_value=None))
    ctx = _ctx()

    await wordpress_handler.upload_WP(ctx)

    publish.assert_not_awaited()
    publish_board_stub.assert_not_awaited()
    # Кнопка под файлом прошлого выпуска: бот говорит, что файл заменён.
    ctx.answer.assert_awaited_once_with(t("episode_file_gone"), alert=True)
