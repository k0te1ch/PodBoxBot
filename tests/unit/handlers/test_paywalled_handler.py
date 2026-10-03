from unittest.mock import AsyncMock, MagicMock

import pytest

from handlers import paywalled_handler
from services.i18n import t
from shared.kafka.models.paywalled_event import PatreonEvent, SponsrEvent, VkEvent

INFO = {"number": "42", "title": "42. Послешоу", "comment": "Описание", "chapters": [["00:00", "Начало"]]}


def _ctx():
    ctx = MagicMock()
    ctx.locale = "ru"
    ctx.answer = AsyncMock()
    ctx.event.from_user.username = "admin"
    ctx.message.audio.file_name = "0042_postshow.mp3"
    status = MagicMock()
    status.chat.id = 100
    status.message_id = 7
    ctx.message.answer = AsyncMock(return_value=status)
    return ctx


@pytest.fixture
def publish(monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(paywalled_handler, "publish_request", mock)
    monkeypatch.setattr(paywalled_handler, "username_of", lambda ctx: "admin")
    return mock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "event_cls"),
    [
        (paywalled_handler.VK, VkEvent),
        (paywalled_handler.PATREON, PatreonEvent),
        (paywalled_handler.SPONSR, SponsrEvent),
    ],
)
async def test_sends_aftershow_event_to_platform_topic(monkeypatch, publish, platform, event_cls, publish_board_stub):
    monkeypatch.setattr(paywalled_handler, "load_template_info", AsyncMock(return_value={"info": INFO}))
    ctx = _ctx()

    await paywalled_handler.upload_to(platform)(ctx)

    _ctx_arg, topic, schema, event = publish.await_args.args
    assert topic == f"publisher.{platform.key}.upload"
    assert schema == f"{platform.key}_event.avsc"
    assert isinstance(event, event_cls)
    assert event.type_episode == "aftershow"
    assert event.path.endswith("0042_postshow.mp3")
    assert (event.chat_id, event.message_id) == ("100", "7")
    assert event.chapters == [["00:00", "Начало"]]
    assert publish_board_stub.await_args.args[1] == platform.key


@pytest.mark.asyncio
async def test_missing_template_info_is_reported(monkeypatch, publish):
    monkeypatch.setattr(paywalled_handler, "load_template_info", AsyncMock(return_value=None))
    ctx = _ctx()

    await paywalled_handler.upload_to(paywalled_handler.VK)(ctx)

    publish.assert_not_awaited()
    # Кнопка под файлом прошлого выпуска: бот говорит, что файл заменён.
    ctx.answer.assert_awaited_once_with(t("episode_file_gone"), alert=True)
