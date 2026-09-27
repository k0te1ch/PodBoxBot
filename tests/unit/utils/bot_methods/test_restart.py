import os
import signal
from unittest.mock import patch

from utils.bot_methods import restart_bot


@patch("utils.bot_methods.os.kill")
def test_restart_bot(mock_kill):
    """restart_bot шлёт SIGINT: бот штатно завершается, docker поднимает его заново."""

    restart_bot()
    mock_kill.assert_called_once_with(os.getpid(), signal.SIGINT)
