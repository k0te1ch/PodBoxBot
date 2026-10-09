import io
import sys
from pathlib import Path
from unittest.mock import ANY, patch

from loguru import logger

from config import FILE_LOG_FORMAT, set_up_logger, with_context


def test_set_up_logger():
    log_level = "DEBUG"
    logs_path = Path("/tmp/test_logs")

    with patch("config.logger.add") as mock_add, patch("config.logger.remove") as mock_remove:
        set_up_logger(log_level, logs_path)

        mock_remove.assert_called_once()
        assert mock_add.call_count == 2

        mock_add.assert_any_call(
            sys.stdout,
            colorize=True,
            format=ANY,
            level=log_level,
            backtrace=False,
            diagnose=False,
        )
        mock_add.assert_any_call(
            logs_path / "file_{time:YYYY-MM-DD_HH-mm-ss}.log",
            rotation="5 MB",
            retention="14 days",
            compression="gz",
            format=ANY,
            level="TRACE",
            backtrace=False,
            diagnose=False,
        )
        assert all(callable(call.kwargs["format"]) for call in mock_add.call_args_list)


def _render(**context: object) -> str:
    sink = io.StringIO()
    handler_id = logger.add(sink, format=with_context(FILE_LOG_FORMAT), level="DEBUG")
    try:
        logger.bind(**context).info("hello")
    finally:
        logger.remove(handler_id)
    return sink.getvalue()


def test_line_without_context_keeps_the_old_format():
    line = _render()

    assert line.rstrip("\n").endswith("| hello")


def test_bound_context_is_appended_to_the_line():
    line = _render(update_id=7, user_id=42)

    assert line.rstrip("\n").endswith("| hello | {'update_id': 7, 'user_id': 42}")
