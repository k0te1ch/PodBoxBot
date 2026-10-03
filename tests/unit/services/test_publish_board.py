"""Табло публикации: одна таблица на все площадки готового файла."""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from fakeredis import FakeAsyncRedis

import config
from services import publish_board
from services.publish_board import DONE, FAILED, QUEUED, RUNNING, PublishBoards, StatusRef
from services.publish_board_store import TTL_SECONDS, BoardStore
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
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


def _use(registry: PublishBoards, monkeypatch) -> PublishBoards:
    monkeypatch.setattr(publish_board, "boards", registry)
    # В пакете services под этим именем лежит объект, а не модуль.
    monkeypatch.setattr(sys.modules["services.telegram_updater"], "boards", registry)
    monkeypatch.setattr(publishing, "boards", registry)
    monkeypatch.setattr(config, "RICH_MESSAGES", True)
    return registry


@pytest.fixture
def boards(clock, redis, monkeypatch) -> PublishBoards:
    return _use(PublishBoards(clock, BoardStore(redis)), monkeypatch)


@pytest.fixture
def restart(clock, redis, monkeypatch):
    """Бот перезапустился: память процесса пуста, Redis тот же."""

    def fresh() -> PublishBoards:
        return _use(PublishBoards(clock, BoardStore(redis)), monkeypatch)

    return fresh


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
    board = await boards.get(CHAT_ID, BOARD_ID)
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
    board = await boards.get(CHAT_ID, BOARD_ID)
    bot.edit_message_text.side_effect = [TelegramRetryAfter(MagicMock(), "Too Many Requests", 4), None]

    await boards.update(board, "ftp", DONE, "✅ файл загружен")

    sleep.assert_awaited_once_with(4)
    assert bot.edit_message_text.await_count == 2


@pytest.mark.asyncio
async def test_event_without_a_board_edits_the_message_as_plain_text(boards, bot):
    """Сообщение, у которого табло нет вовсе, правится текстом, как раньше."""
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
    board = await boards.get(CHAT_ID, BOARD_ID)
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


@pytest.mark.asyncio
async def test_event_after_a_restart_still_edits_the_board_as_a_table(boards, bot, restart):
    """Перезапуск посреди публикации: итог приходит в то же табло, таблицей."""
    audio = _audio(bot)
    await boards.open(audio, "ftp", TITLE)
    await boards.open(audio, "wp", TITLE)
    await TelegramUpdater(bot).update_upload_progress(_event("ftp", number=None), finished=True)
    restart()
    bot.edit_message_text.reset_mock()

    await TelegramUpdater(bot).update_upload_result(
        _event("wp", metadata={"platform": "wp", "action": "draft"}), success=True
    )

    bot.edit_message_text.assert_awaited_once()
    assert bot.edit_message_text.await_args.kwargs["message_id"] == BOARD_ID
    html = _html(bot)
    assert "<td>FTP</td><td>✅ файл загружен</td>" in html
    assert "<td>Сайт</td><td>✅ черновик сохранён, подписчики его пока не видят</td>" in html


@pytest.mark.asyncio
async def test_button_after_a_restart_adds_a_row_to_the_old_board(boards, bot, restart):
    audio = _audio(bot)
    await boards.open(audio, "ftp", TITLE)
    await TelegramUpdater(bot).update_upload_progress(_event("ftp", number=None), finished=True)

    ref = await restart().open(audio, "wp", TITLE)

    assert ref == StatusRef(CHAT_ID, BOARD_ID)
    bot.send_rich_message.assert_awaited_once()
    assert "<td>FTP</td><td>✅ файл загружен</td>" in _html(bot)
    assert "<td>Сайт</td><td>⏳ отправляю запрос</td>" in _html(bot)


@pytest.mark.asyncio
async def test_progress_after_a_restart_does_not_overwrite_the_result(boards, bot, restart, clock):
    await boards.open(_audio(bot), "ftp", TITLE)
    await TelegramUpdater(bot).update_upload_progress(_event("ftp", number=None), finished=True)
    registry = restart()
    clock.now += 60
    bot.edit_message_text.reset_mock()

    await TelegramUpdater(bot).update_upload_progress(_event("ftp", number=None, status="uploading", progress=0.5))

    bot.edit_message_text.assert_not_awaited()
    restored = await registry.get(CHAT_ID, BOARD_ID)
    assert restored.rows["ftp"].state == DONE


@pytest.mark.asyncio
async def test_events_at_once_after_a_restart_share_one_board(boards, bot, restart):
    """Два события сразу после перезапуска поднимают одно табло с одним
    замком: правки идут по одной, в сообщении остаётся итог обеих площадок."""
    import asyncio

    audio = _audio(bot)
    await boards.open(audio, "ftp", TITLE)
    await boards.open(audio, "wp", TITLE)
    registry = restart()
    sent: list[str] = []

    async def slow_edit(**kwargs):
        await asyncio.sleep(0)
        sent.append(kwargs["rich_message"].html)

    bot.edit_message_text = AsyncMock(side_effect=slow_edit)
    updater = TelegramUpdater(bot)

    await asyncio.gather(
        updater.update_upload_progress(_event("ftp", number=None), finished=True),
        updater.update_upload_result(_event("wp", metadata={"action": "published"}), success=True),
    )

    assert "✅ файл загружен" in sent[-1] and "✅ опубликовано" in sent[-1]
    assert len(registry._by_status) == 1


@pytest.mark.asyncio
async def test_deleted_board_is_sent_again_and_keeps_its_address(boards, bot, restart, clock):
    """Табло удалили из чата, а публикация ещё идёт: итог приходит новым
    сообщением, следующие события правят уже его."""
    await boards.open(_audio(bot), "ftp", TITLE)
    bot.send_rich_message = AsyncMock(return_value=MagicMock(message_id=90))
    bot.edit_message_text.side_effect = TelegramBadRequest(MagicMock(), "Bad Request: message to edit not found")
    updater = TelegramUpdater(bot)
    clock.now += 10

    await updater.update_upload_progress(_event("ftp", status="pending", metadata={"stage": "upload"}))

    # Одна попытка правки: обычным текстом удалённое сообщение не правится.
    bot.edit_message_text.assert_awaited_once()
    assert "⏳ загрузка файла на FTP" in bot.send_rich_message.await_args.kwargs["rich_message"].html

    bot.edit_message_text = AsyncMock()
    restart()
    await TelegramUpdater(bot).update_upload_progress(_event("ftp", number=None), finished=True)

    assert bot.edit_message_text.await_args.kwargs["message_id"] == 90
    assert "✅ файл загружен" in _html(bot)
    bot.send_rich_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_board_is_kept_for_thirty_days(boards, bot, redis):
    await boards.open(_audio(bot), "ftp", TITLE)

    assert TTL_SECONDS == 30 * 24 * 3600
    for key in (f"publish:board:{CHAT_ID}:{BOARD_ID}", f"publish:audio:{CHAT_ID}:{AUDIO_ID}"):
        assert TTL_SECONDS - 5 <= await redis.ttl(key) <= TTL_SECONDS
    assert await redis.zrange("publish:recent", 0, -1) == [f"{CHAT_ID}:{BOARD_ID}"]


@pytest.mark.asyncio
async def test_recent_boards_survive_a_restart(bot, clock, redis, restart, monkeypatch):
    moments = iter([1_000.0, 2_000.0])
    registry = _use(PublishBoards(clock, BoardStore(redis, clock=lambda: next(moments))), monkeypatch)
    await registry.open(_audio(bot), "ftp", TITLE)
    bot.send_rich_message = AsyncMock(return_value=MagicMock(message_id=BOARD_ID + 1))
    await registry.open(_audio(bot, message_id=51), "wp", "Выпуск 1003: публикация")
    registry = restart()
    registry.bind(bot)

    recent = await registry.recent(5)

    assert [board.title for board in recent] == ["Выпуск 1003: публикация", TITLE]


@pytest.mark.asyncio
async def test_board_works_from_memory_when_redis_is_down(bot, clock, monkeypatch):
    broken = MagicMock()
    for command in ("set", "get", "zadd", "zrevrange"):
        setattr(broken, command, AsyncMock(side_effect=ConnectionError("redis is down")))
    registry = _use(PublishBoards(clock, BoardStore(broken)), monkeypatch)
    audio = _audio(bot)

    await registry.open(audio, "ftp", TITLE)
    await registry.open(audio, "wp", TITLE)
    await TelegramUpdater(bot).update_upload_progress(_event("ftp", number=None), finished=True)

    bot.send_rich_message.assert_awaited_once()
    assert "<td>FTP</td><td>✅ файл загружен</td>" in _html(bot)
