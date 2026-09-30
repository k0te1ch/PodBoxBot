"""Кнопка «Сайт» для шаблона без Tags и Chapters (оба поля в шаблоне необязательны)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from handlers import wordpress_handler
from utils.validators import validate_template

TEMPLATE = "Number: 768\nTitle: Эпизод без таймкодов\nComment: Описание"


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.locale = "ru"
    ctx.answer = AsyncMock()
    ctx.message.audio.file_name = "0768_rz_30092026.mp3"
    ctx.message.audio.duration = 3725
    status = MagicMock(message_id=7)
    status.chat.id = 100
    ctx.message.answer = AsyncMock(return_value=status)
    return ctx


@pytest.mark.asyncio
async def test_site_button_publishes_template_without_chapters(monkeypatch):
    info = validate_template(TEMPLATE)
    assert "chapters" not in info and "tags" not in info

    stored = {"info": info, "type_episode": "main"}
    monkeypatch.setattr(wordpress_handler, "load_template_info", AsyncMock(return_value=stored))
    monkeypatch.setattr(wordpress_handler, "username_of", lambda ctx: "admin")
    publish = AsyncMock(return_value=True)
    monkeypatch.setattr(wordpress_handler, "publish_request", publish)

    # Раньше info["chapters"] падал KeyError, и пользователь не получал ответа.
    await wordpress_handler.upload_WP(_ctx())

    event = publish.await_args.args[3]
    assert event.chapters == []
    assert event.tags == []
    assert (event.number, event.title, event.slug) == ("768", "768. Эпизод без таймкодов", "0768_rz_30092026")
