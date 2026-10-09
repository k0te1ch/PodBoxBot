"""Собственные сообщения бота админам не выносят секреты в чат.

Отчёты об ошибках и журнал маскирует SDK. Здесь проверяются места, где бот
сам вставляет в сообщение текст исключения или ответ внешней системы: табло
публикации, старый статус без табло, сбой отправки в очередь, пересылка в
чат, ответ FTP и предупреждение о ленте RSS.
"""

import ftplib
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendAudio
from fakeredis import FakeAsyncRedis
from pydantic import BaseModel
from sagenza_tgbot_sdk.masking import default_masker, register_secrets

import config
from config import register_settings_secrets
from handlers import audio_handler
from services import publish_board
from services.publish_board import FAILED, RETRY, Board, PublishBoards
from services.publish_board_store import BoardStore
from services.rss import RssWatcher
from services.telegram_updater import TelegramUpdater
from shared.secret_masking import register_named_secrets
from utils import publishing
from utils.ftp_methods import EpisodeNumberError, get_last_post_id
from utils.safe_text import safe_html, safe_text

# Собраны из частей: значения не похожи на настоящие и не цепляют сканеры секретов.
SECRET = "Sftp)" + "pass&0123"
SHORT = "x" + "7Qz"
LOGIN = "podcast"
LEAK = f"530 Login incorrect for {LOGIN}/{SHORT}, sftp://{LOGIN}:{SECRET}@ftp.example.com said {SECRET}"

BOT_SOURCES = Path(__file__).resolve().parents[3] / "app" / "bot"


@pytest.fixture(autouse=True)
def secrets():
    """Длинный секрет площадки и короткий пароль FTP, как их зарегистрировал бы бот."""
    register_secrets(SECRET)
    register_named_secrets({"FTP_PASSWORD": SHORT}, logins=[LOGIN])
    yield
    default_masker.clear()
    register_settings_secrets(config.settings)


def _clean(text: str) -> bool:
    return SECRET not in text and SHORT not in text and "pass&amp;0123" not in text


def test_safe_text_masks_long_and_short_secrets():
    masked = safe_text(RuntimeError(LEAK))

    assert _clean(masked)
    assert masked.startswith(f"530 Login incorrect for {LOGIN}/***")


def test_safe_html_masks_before_escaping():
    """После экранирования ``&`` в секрете стал бы ``&amp;`` и не совпал бы."""
    masked = safe_html(f"<b>{SECRET}</b>")

    assert masked == "&lt;b&gt;***&lt;/b&gt;"


@pytest.fixture
def board_bot() -> MagicMock:
    bot = MagicMock()
    bot.edit_message_text = AsyncMock()
    bot.send_rich_message = AsyncMock(return_value=MagicMock(message_id=77))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=77))
    return bot


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [FAILED, RETRY])
async def test_publish_board_keeps_the_error_without_secrets(board_bot, state):
    """Ошибка публишера из Kafka: без секретов и в табло, и в Redis."""
    redis = FakeAsyncRedis(decode_responses=True)
    boards = PublishBoards(lambda: 1000.0, BoardStore(redis))
    board = Board(board_bot, 100, 77, "Выпуск 1002: публикация")

    await boards.update(board, "ftp", state, "❌ ошибка", error=LEAK)

    assert _clean(board.rows["ftp"].error)
    assert _clean(board.html()) and "***" in board.html()
    assert _clean(board.text()) and "***" in board.text()
    stored = "".join([str(await redis.get(key)) async for key in redis.scan_iter("publish:board:*")])
    assert stored and _clean(stored)


def test_board_restored_from_redis_is_masked_on_render(board_bot):
    """Табло, сохранённое до появления маскировки, показывается уже без секретов."""
    board = Board(board_bot, 100, 77, "Выпуск 1002: публикация")
    board.rows["ftp"] = publish_board.Row("ftp", state=FAILED, text="❌ ошибка", error=LEAK)

    assert _clean(board.html())
    assert _clean(board.text())


@pytest.mark.asyncio
async def test_status_without_a_board_masks_the_publisher_error():
    bot = AsyncMock()
    updater = TelegramUpdater(bot)
    event = {"chat_id": "123", "message_id": "456", "number": "1002"}

    await updater.update_upload_result(event, success=False, error=LEAK)

    text = bot.edit_message_text.call_args.kwargs["text"]
    assert "Ошибка публикации" in text and "***" in text
    assert _clean(text)


@pytest.mark.asyncio
async def test_retry_status_without_a_board_masks_the_publisher_error():
    bot = AsyncMock()
    updater = TelegramUpdater(bot)
    event = {"chat_id": "123", "message_id": "456", "file_name": "1002_rz.mp3", "error": LEAK, "metadata": {}}

    await updater.update_upload_retry(event)

    text = bot.edit_message_text.call_args.kwargs["text"]
    assert "***" in text
    assert _clean(text)


class _Event(BaseModel):
    file_name: str = "1002_rz.mp3"


@pytest.mark.asyncio
async def test_queue_failure_status_masks_the_exception():
    ctx = MagicMock(answer=AsyncMock(), locale="ru")
    status = MagicMock(edit_text=AsyncMock())
    producer = MagicMock(send=AsyncMock(side_effect=RuntimeError(LEAK)))
    with patch.object(publishing, "KafkaProducer", return_value=producer):
        await publishing.publish_request(ctx, "topic", "x.avsc", _Event(), status=status, title="FTP")

    text = status.edit_text.call_args.args[0]
    assert text.startswith("❌ FTP") and "RuntimeError: 530 Login incorrect" in text
    assert _clean(text)


def test_forward_error_text_is_masked():
    error = TelegramBadRequest(method=SendAudio(chat_id=1, audio="x"), message=f"Bad Request: {LEAK}")

    text = audio_handler.explain_telegram_error(error, "Аудио не отправлено", chat="@chat")

    assert text.startswith("Аудио не отправлено: ") and "***" in text
    assert _clean(text)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ftplib.error_perm(LEAK), OSError(LEAK)], ids=["refused", "no_reply"])
async def test_ftp_answer_is_masked_in_the_episode_number_error(error):
    with (
        patch("utils.ftp_methods.ftplib.FTP_TLS", MagicMock(side_effect=error)),
        pytest.raises(EpisodeNumberError) as raised,
    ):
        await get_last_post_id("main", "srv", LOGIN, SHORT)

    assert "530 Login incorrect" in str(raised.value)
    assert _clean(str(raised.value))


@pytest.mark.asyncio
async def test_rss_alert_hides_credentials_of_the_feed_address():
    bot = MagicMock(send_message=AsyncMock())
    feed = f"https://{LOGIN}:{SECRET}@example.com/feed?token={SHORT}"
    watcher = RssWatcher(bot, MagicMock(), feed, [1], interval=600, failure_alert=1)
    with patch.object(watcher, "fetch", AsyncMock(side_effect=OSError("down"))):
        await watcher.tick()

    text = bot.send_message.await_args.args[1]
    assert "example.com/feed" in text
    assert _clean(text)


UNMASKED = re.compile(
    r"escape\(str\((?:e|err|error|exc)\)\)"
    r"|\{type\((?:e|err|error|exc)\)\.__name__\}: \{(?:e|err|error|exc)\}"
)


def test_no_exception_text_is_escaped_without_masking():
    """Сторож: новый текст исключения в сообщении идёт через ``safe_html``
    или ``format_error``, а не через ``escape(str(e))``. Строки журнала не в
    счёт: их маскирует патчер loguru."""
    offenders = [
        f"{path.relative_to(BOT_SOURCES)}:{number}"
        for path in BOT_SOURCES.rglob("*.py")
        if ".venv" not in path.parts
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if UNMASKED.search(line) and "logger." not in line
    ]

    assert offenders == []
