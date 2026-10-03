"""``/status``: состояние бота и последние публикации таблицей."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import config
from handlers import status_handler
from services.i18n import t
from services.publish_board import DONE, Board, PublishBoards, Row


@pytest.fixture
def boards(monkeypatch) -> PublishBoards:
    registry = PublishBoards()
    monkeypatch.setattr(status_handler, "boards", registry)
    monkeypatch.setattr(status_handler, "get_version", AsyncMock(return_value="0.10.0"))
    monkeypatch.setattr(config, "TOPICS_ENABLED", False)
    return registry


@pytest.mark.asyncio
async def test_status_lists_the_bot_facts(boards):
    metrics = MagicMock(totals=MagicMock(return_value={"updates": 12.0, "errors": 1.0}))

    html, text = await status_handler.render(metrics, "ru")

    assert html.startswith(f"<h4>{t('status_title')}</h4><table bordered striped>")
    assert f"<td>{t('status_version')}</td><td>0.10.0</td>" in html
    assert f"<td>{t('status_updates')}</td><td>12</td>" in html
    assert f"<td>{t('status_topics')}</td><td>{t('status_off')}</td>" in html
    assert t("status_publications_none") in html
    assert f"{t('status_version')}: 0.10.0" in text


@pytest.mark.asyncio
async def test_status_shows_recent_publications_by_platform(boards):
    board = Board(MagicMock(), 1, 2, "Выпуск 1002: публикация")
    board.rows["wp"] = Row("wp", DONE, "✅ черновик сохранён")
    boards._by_audio[(1, 50)] = board

    html, text = await status_handler.render(None, "ru")

    assert f"<h4>{t('status_publications')}</h4>" in html
    assert "<td>Выпуск 1002</td><td>Сайт</td><td>✅ черновик сохранён</td>" in html
    assert "Выпуск 1002 · Сайт · ✅ черновик сохранён" in text


@pytest.mark.asyncio
async def test_status_command_answers_with_a_rich_message(boards, monkeypatch):
    monkeypatch.setattr(config, "RICH_MESSAGES", True)
    bot = MagicMock(send_rich_message=AsyncMock())
    msg = MagicMock()
    msg.chat.id = 5

    await status_handler.status(msg, bot, "ru")

    assert bot.send_rich_message.await_args.kwargs["chat_id"] == 5
