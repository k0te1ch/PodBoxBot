import sys
from pathlib import Path
from unittest.mock import patch

from app.config import set_up_logger  # Замените на имя вашего модуля


def test_set_up_logger():
    # Mock log level and logs path
    log_level = "DEBUG"
    logs_path = Path("/tmp/test_logs")

    # Mock methods of loguru logger
    with patch("app.config.logger.add") as mock_add, patch("app.config.logger.remove") as mock_remove:
        set_up_logger(log_level, logs_path)

        # Assert logger.remove was called
        mock_remove.assert_called_once()

        # Assert logger.add was called twice
        assert mock_add.call_count == 2

        # Check the first call to logger.add (stdout handler)
        mock_add.assert_any_call(
            sys.stdout,
            colorize=True,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level>::<blue>{module}</blue>::<cyan>{function}</cyan>::<cyan>{line}</cyan> | <level>{message}</level>",
            level=log_level,
            backtrace=True,
            diagnose=True,
        )

        # Check the second call to logger.add (file handler)
        expected_file_path = logs_path / "file_{time:YYYY-MM-DD_HH-mm-ss}.log"
        mock_add.assert_any_call(
            expected_file_path,
            rotation="5 MB",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level}::{module}::{function}::{line} | {message}",
            level="TRACE",
            backtrace=True,
            diagnose=True,
        )
