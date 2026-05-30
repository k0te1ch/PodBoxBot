import os
import signal
from unittest.mock import patch

from utils.bot_methods import shutdown_bot


@patch("utils.bot_methods.os.kill")
def test_shutdown_bot(mock_kill):
    """shutdown_bot шлёт SIGINT текущему процессу для корректного завершения."""

    shutdown_bot()
    mock_kill.assert_called_once_with(os.getpid(), signal.SIGINT)
