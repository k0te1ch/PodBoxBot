import io
from unittest.mock import patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from loguru import logger

import main
from config import FILE_LOG_FORMAT, with_context


def test_sdk_installs_bot_modules():
    dp = Dispatcher()
    with patch.object(main, "ADMINS_ID", [1]):
        main._setup_sdk(dp)

    assert set(dp.workflow_data["sdk"].modules) == {
        "logging",
        "metrics",
        "notify",
        "health",
        "status",
        "host_watch",
        "menus",
    }


@pytest.mark.asyncio
async def test_update_context_reaches_the_log_line():
    dp = Dispatcher()
    with patch.object(main, "ADMINS_ID", [1]):
        main._setup_sdk(dp)
    bot = Bot("42:TEST")
    update = Update.model_validate(
        {
            "update_id": 7,
            "message": {
                "message_id": 1,
                "date": 0,
                "chat": {"id": 100, "type": "private"},
                "from": {"id": 100, "is_bot": False, "first_name": "A"},
                "text": "hi",
            },
        }
    )
    sink = io.StringIO()
    handler_id = logger.add(sink, format=with_context(FILE_LOG_FORMAT), level="DEBUG")
    try:
        await dp.feed_update(bot, update)
    finally:
        logger.remove(handler_id)
        await bot.session.close()

    line = next(line for line in sink.getvalue().splitlines() if "update handled" in line)
    assert "'update_id': 7" in line
    assert "'chat_id': 100" in line


def test_sdk_keeps_the_bot_loguru_sinks():
    dp = Dispatcher()
    with patch.object(main, "ADMINS_ID", [1]), patch("sagenza_tgbot_sdk.logs.module.setup_logging") as setup_logging:
        main._setup_sdk(dp)

    setup_logging.assert_not_called()
    assert dp.workflow_data["sdk"].modules["logging"].settings.configure is False


def test_notify_is_skipped_without_admins():
    dp = Dispatcher()
    with patch.object(main, "ADMINS_ID", []):
        main._setup_sdk(dp)

    assert "notify" not in dp.workflow_data["sdk"].modules


def test_disk_threshold_comes_from_config():
    dp = Dispatcher()
    with (
        patch.object(main, "ADMINS_ID", [1]),
        patch.object(main, "DISK_ALERT_PERCENT", 70.0),
        patch.object(main, "DISK_CHECK_INTERVAL", 60),
    ):
        main._setup_sdk(dp)

    settings = dp.workflow_data["sdk"].modules["host_watch"]._settings
    assert (settings.threshold_percent, settings.interval_seconds) == (70.0, 60)


def test_bot_replies_survive_a_deleted_message():
    """Ответ на удалённое сообщение уходит без привязки, а не падает REPLY_TO_INVALID."""
    bot = main._get_bot_obj()

    assert bot.default.allow_sending_without_reply is True
