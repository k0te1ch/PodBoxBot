"""Отчёт о необработанной ошибке: кому уходит и что в нём нет секретов."""

import io
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Update
from loguru import logger
from sagenza_tgbot_sdk.masking import default_masker, register_secrets

import config
import main
from config import FILE_LOG_FORMAT, register_settings_secrets, with_context

# Собраны из частей: значения не похожи на настоящие и не цепляют сканеры секретов.
BOT_TOKEN = "123456:" + "AaBbCcDdEe" * 4
PLATFORM_SECRET = "vk1.a." + "platform-secret-value"
DEVELOPER_ID = 999
ADMIN_IDS = [1, 2]
USER_ID = 100


@pytest.fixture
def clean_masker():
    yield
    default_masker.clear()
    register_settings_secrets(config.settings)


def _update(update_id: int = 7) -> Update:
    return Update.model_validate(
        {
            "update_id": update_id,
            "message": {
                "message_id": 1,
                "date": 0,
                "chat": {"id": USER_ID, "type": "private"},
                "from": {"id": USER_ID, "is_bot": False, "first_name": "A"},
                "text": "hi",
            },
        }
    )


def _failing_router() -> Router:
    router = Router()

    @router.message()
    async def fail(message) -> None:
        url = f"http://api:8081/file/bot{BOT_TOKEN}/music/file_1.mp3"
        raise ConnectionError(f"404, message='Not Found', url='{url}' ({PLATFORM_SECRET}) <x>")

    return router


async def _feed(developer: int | None, updates: int = 1) -> tuple[AsyncMock, str]:
    """Прогоняет сбойный апдейт через диспетчер бота; возвращает отправки и лог."""
    dp = Dispatcher()
    with patch.object(main, "ADMINS_ID", ADMIN_IDS), patch.object(main, "DEVELOPER", developer):
        main._setup_sdk(dp)
    dp.include_router(_failing_router())
    register_secrets(PLATFORM_SECRET)
    bot = Bot(BOT_TOKEN)
    sink = io.StringIO()
    handler_id = logger.add(sink, format=with_context(FILE_LOG_FORMAT), level="DEBUG")
    try:
        with patch.object(Bot, "send_message", AsyncMock()) as send_message:
            for number in range(updates):
                await dp.feed_update(bot, _update(number))
    finally:
        logger.remove(handler_id)
        await bot.session.close()
    return send_message, sink.getvalue()


@pytest.mark.asyncio
async def test_report_goes_to_the_developer_only(clean_masker):
    send_message, _ = await _feed(DEVELOPER_ID)

    send_message.assert_awaited_once()
    chat_id, text = send_message.await_args.args
    assert chat_id == DEVELOPER_ID
    assert "Unhandled error" in text
    assert "ConnectionError" in text
    assert f"user {USER_ID}, chat {USER_ID}" in text
    # Хвост трейсбека: по нему видно, где упало.
    assert "<pre>" in text
    assert "in fail" in text


@pytest.mark.asyncio
async def test_report_has_no_secrets_and_is_valid_html(clean_masker):
    send_message, _ = await _feed(DEVELOPER_ID)

    text = send_message.await_args.args[1]
    assert BOT_TOKEN not in text
    assert BOT_TOKEN.split(":")[1] not in text
    assert PLATFORM_SECRET not in text
    assert "/file/bot***/music/file_1.mp3" in text
    assert "&lt;x&gt;" in text
    assert len(text) < 4096


@pytest.mark.asyncio
async def test_error_log_has_no_secrets(clean_masker):
    _, log = await _feed(DEVELOPER_ID)

    assert "unhandled error in update handler" in log
    assert "ConnectionError" in log
    assert BOT_TOKEN not in log
    assert PLATFORM_SECRET not in log


@pytest.mark.asyncio
async def test_admins_and_the_user_get_nothing(clean_masker):
    """Как и раньше: о сбое знает только разработчик, в чат ничего не пишется."""
    send_message, _ = await _feed(DEVELOPER_ID)

    recipients = {call.args[0] for call in send_message.await_args_list}
    assert recipients == {DEVELOPER_ID}
    assert not recipients & {*ADMIN_IDS, USER_ID}


@pytest.mark.asyncio
async def test_without_developer_the_error_is_only_logged(clean_masker):
    send_message, log = await _feed(None)

    send_message.assert_not_awaited()
    assert "unhandled error in update handler" in log


@pytest.mark.asyncio
async def test_repeated_error_is_reported_once_per_cooldown(clean_masker):
    send_message, log = await _feed(DEVELOPER_ID, updates=3)

    send_message.assert_awaited_once()
    assert log.count("unhandled error in update handler") == 3
