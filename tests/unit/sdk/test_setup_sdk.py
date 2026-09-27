from unittest.mock import patch

from aiogram import Dispatcher

import main


def test_sdk_installs_bot_modules():
    dp = Dispatcher()
    with patch.object(main, "ADMINS_ID", [1]):
        main._setup_sdk(dp)

    assert set(dp.workflow_data["sdk"].modules) == {"metrics", "notify", "health", "status"}


def test_notify_is_skipped_without_admins():
    dp = Dispatcher()
    with patch.object(main, "ADMINS_ID", []):
        main._setup_sdk(dp)

    assert "notify" not in dp.workflow_data["sdk"].modules
