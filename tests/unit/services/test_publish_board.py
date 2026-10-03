"""Табло публикации: одна таблица на все площадки готового файла."""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

import config
from services import publish_board
from services.publish_board import DONE, FAILED, QUEUED, RUNNING, PublishBoards, StatusRef
from services.telegram_updater import PLATFORM_KEY, TelegramUpdater
from utils import publishing

CHAT_ID = 100
AUDIO_ID = 50
BOARD_ID = 77
TITLE = "Выпуск 1002: публикация"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def bot() -> MagicMock:
    bot = MagicMock()
    bot.send_rich_message = AsyncMock(return_value=MagicMock(message_id=BOARD_ID))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=BOARD_ID))
    bot.edit_message_text = AsyncMock()
    return bot


@pytest.fixture
def boards(clock, monkeypatch) -> PublishBoards:
    registry = PublishBoards(clock)
    monkeypatch.setattr(publish_board, "boards", registry)
    # В пакете services под этим именем лежит объект, а не модуль.
    monkeypatch.setattr(sys.modules["services.telegram_updater"], "boards", registry)
    monkeypatch.setattr(publishing, "boards", registry)
    monkeypatch.setattr(config, "RICH_MESSAGES", True)
    return registry


def _audio(bot, message_id: int = AUDIO_ID) -> MagicMock:
    audio = MagicMock(message_id=message_id, bot=bot)
    audio.chat.id = CHAT_ID
    return audio


def _html(bot) -> str:
    return bot.edit_message_text.await_args.kwargs["rich_message"].html


def _event(platform: str, **fields) -> dict:
    return {"chat_id": str(CHAT_ID), "message_id": str(BOARD_ID), "number": "1002", PLATFORM_KEY: platform, **fields}


@pytest.mark.asyncio
async def test_first_button_sends_the_board_as_a_table(boards, bot):
    ref = await boards.open(_audio(bot), "ftp", TITLE)

    assert ref == StatusRef(CHAT_ID, BOARD_ID)
    html = bot.send_rich_message.await_args.kwargs["rich_message"].html
    assert html.startswith(f"<h4>{TITLE}</h4><table bordered striped>")
    for header in ("Площадка", "Состояние", "Ссылка", "Когда"):
        assert f"<th>{header}</th>" in html
    assert "<td>FTP</td><td>⏳ отправляю запрос</td>" in html


@pytest.mark.asyncio
async def test_next_platform_adds_a_row_to_the_same_message(boards, bot):
    """Сайт после FTP не присылает второе сообщение: в табло появляется строка."""
    audio = _audio(bot)
    await boards.open(audio, "ftp", TITLE)

    ref = await boards.open(audio, "wp", TITLE)

    assert ref == StatusRef(CHAT_ID, BOARD_ID)
    bot.send_rich_message.assert_awaited_once()
    assert bot.edit_message_text.await_args.kwargs["message_id"] == BOARD_ID
    assert "<td>FTP</td>" in _html(bot) and "<td>Сайт</td>" in _html(bot)


@pytest.mark.asyncio
async def test_another_file_gets_its_own_board(boards, bot):
    await boards.open(_audio(bot), "ftp", TITLE)

    await boards.open(_audio(bot, message_id=51), "ftp", "Выпуск 1003: публикация")

    assert bot.send_rich_message.await_count == 2


@pytest.mark.asyncio
async def test_events_fill_the_rows_with_state_link_time_and_error(boards, bot):
    audio = _audio(bot)
    await boards.open(audio, "ftp", TITLE)
    await boards.open(audio, "wp", TITLE)
    await boards.open(audio, "boosty", TITLE)
    updater = TelegramUpdater(bot)

    await updater.update_upload_progress(_event("ftp", number=None, file_name="1002_rz.mp3"), finished=True)
    await updater.update_upload_progress(_event("wp", status="pending", metadata={"stage": "verify"}))
    await updater.update_upload_result(
        _event(
            "wp", metadata={"platform": "wp", "action": "draft", "url": "https://example.org/wp-admin/post.php?post=9"}
        ),
        success=True,
    )
    await updater.update_upload_result(
        _event("boosty", metadata={"stage": "publish"}), success=False, error="403 <Forbidden>"
    )

    html = _html(bot)
    assert "<td>FTP</td><td>✅ файл загружен</td>" in html
    assert (
        "<td>Сайт</td><td>✅ черновик сохранён, подписчики его пока не видят</td>"
        '<td><a href="https://example.org/wp-admin/post.php?post=9">открыть</a></td>'
    ) in html
    assert "<td>Boosty</td><td>❌ ошибка на шаге «публикация поста»</td>" in html
    assert "<p>❌ <b>Boosty</b>: <code>403 &lt;Forbidden&gt;</code></p>" in html
    board = boards.get(CHAT_ID, BOARD_ID)
    assert [row.state for row in board.rows.values()] == [DONE, DONE, FAILED]


@pytest.mark.asyncio
async def test_retry_is_shown_with_the_attempt_and_the_reason(boards, bot):
    await boards.open(_audio(bot), "wp", TITLE)

    await TelegramUpdater(bot).update_upload_retry(
        _event("wp", error="502", metadata={"attempt": "2", "attempts": "3", "stage": "publish"})
    )

    assert "🔁 попытка 2/3 не удалась на шаге «публикация поста», повторяю" in _html(bot)
    assert "<code>502</code>" in _html(bot)


@pytest.mark.asyncio
async def test_upload_progress_is_throttled_and_never_overwrites_the_result(boards, bot, clock):
    await boards.open(_audio(bot), "ftp", TITLE)
    updater = TelegramUpdater(bot)
    progress = {"number": None, "file_name": "1002_rz.mp3", "status": "uploading"}

    for step in range(1, 11):
        clock.now += 0.5
        await updater.update_upload_progress(_event("ftp", progress=step / 10, **progress))
    # Пять секунд хода: две правки, а не десять.
    assert bot.edit_message_text.await_count == 2
    assert "📤" in _html(bot)

    await updater.update_upload_progress(_event("ftp", **progress), finished=True)
    edits = bot.edit_message_text.await_count
    clock.now += 10
    await updater.update_upload_progress(_event("ftp", progress=0.5, **progress))

    assert bot.edit_message_text.await_count == edits
    assert "✅ файл загружен" in _html(bot)


@pytest.mark.asyncio
async def test_board_falls_back_to_text_when_rich_is_refused(boards, bot):
    bot.send_rich_message.side_effect = TelegramBadRequest(MagicMock(), "RICH_MESSAGE_INVALID")

    await boards.open(_audio(bot), "ftp", TITLE)

    text = bot.send_message.await_args.kwargs["text"]
    assert text.startswith(f"<b>{TITLE}</b>\nFTP: ⏳ отправляю запрос")


@pytest.mark.asyncio
async def test_final_state_waits_out_the_flood_limit(boards, bot, monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(publish_board.asyncio, "sleep", sleep)
    await boards.open(_audio(bot), "ftp", TITLE)
    board = boards.get(CHAT_ID, BOARD_ID)
    bot.edit_message_text.side_effect = [TelegramRetryAfter(MagicMock(), "Too Many Requests", 4), None]

    await boards.update(board, "ftp", DONE, "✅ файл загружен")

    sleep.assert_awaited_once_with(4)
    assert bot.edit_message_text.await_count == 2


@pytest.mark.asyncio
async def test_event_without_a_board_edits_the_message_as_plain_text(boards, bot):
    """После перезапуска бота табло в памяти нет: сообщение правится текстом, как раньше."""
    await TelegramUpdater(bot).update_upload_result(
        _event("wp", metadata={"platform": "wp", "action": "draft"}), success=True
    )

    assert bot.edit_message_text.await_args.kwargs["text"].startswith("✅ Эпизод <b>1002</b>: пост сохранён")


@pytest.mark.asyncio
async def test_queue_state_and_send_failure_go_to_the_row(boards, bot):
    ref = await boards.open(_audio(bot), "wp", TITLE)

    assert await publishing._set_board(ref, "wp", QUEUED, publish_board.QUEUED_TEXT) is True
    assert "⏳ запрос принят, жду сервис публикации" in _html(bot)
    assert await publishing._set_board(ref, "wp", FAILED, publishing.FAILED_ROW, error="KafkaError: down") is True
    assert "<code>KafkaError: down</code>" in _html(bot)
    assert await publishing._set_board(StatusRef(1, 2), "wp", RUNNING, "x") is False


@pytest.mark.asyncio
async def test_overlapping_updates_leave_the_latest_state_in_the_message(boards, bot):
    """Результат площадки и «запрос принят» от кнопки приходят одновременно.

    Telegram отменяет правку, которую догнала следующая. Правки идут по
    одной и каждая несёт свежее состояние: итог не теряется.
    """
    import asyncio

    await boards.open(_audio(bot), "ftp", TITLE)
    board = boards.get(CHAT_ID, BOARD_ID)
    sent: list[str] = []

    async def slow_edit(**kwargs):
        await asyncio.sleep(0)
        sent.append(kwargs["rich_message"].html)

    bot.edit_message_text = AsyncMock(side_effect=slow_edit)

    await asyncio.gather(
        boards.update(board, "ftp", DONE, "✅ файл загружен"),
        boards.update(board, "ftp", QUEUED, publish_board.QUEUED_TEXT),
    )

    assert "✅ файл загружен" in sent[-1]
    assert all("жду сервис публикации" not in html for html in sent)


@pytest.mark.asyncio
async def test_two_buttons_at_once_share_one_board(boards, bot):
    import asyncio

    audio = _audio(bot)

    first, second = await asyncio.gather(boards.open(audio, "ftp", TITLE), boards.open(audio, "wp", TITLE))

    assert first == second == StatusRef(CHAT_ID, BOARD_ID)
    bot.send_rich_message.assert_awaited_once()
