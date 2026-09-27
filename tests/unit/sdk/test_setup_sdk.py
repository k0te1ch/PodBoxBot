from unittest.mock import patch

from aiogram import Dispatcher

import main


def test_sdk_installs_bot_modules():
    dp = Dispatcher()
    with patch.object(main, "ADMINS_ID", [1]):
        main._setup_sdk(dp)

    assert set(dp.workflow_data["sdk"].modules) == {"metrics", "notify", "health", "status", "host_watch", "menus"}


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
