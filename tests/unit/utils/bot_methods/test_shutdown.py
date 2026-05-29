from unittest.mock import patch

from app.utils.bot_methods import shutdown_bot


@patch("builtins.exit")
def test_shutdown_bot(mock_exit):
    """Тестирование того, что shutdown_bot вызывает exit"""

    shutdown_bot()
    mock_exit.assert_called_once()
