"""Tests for the global dp.errors error reporter (utils/error_reporting.py)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from utils import error_reporting


def _make_event(exc, *, username="alice", user_id=42):
    user = MagicMock()
    user.username = username
    user.id = user_id
    msg = MagicMock()
    msg.from_user = user
    update = MagicMock(message=msg, edited_message=None, callback_query=None, my_chat_member=None, chat_member=None)
    event = MagicMock()
    event.update = update
    event.exception = exc
    return event


@pytest.mark.asyncio
async def test_notify_developer_sends_message(monkeypatch):
    monkeypatch.setattr(error_reporting, "DEVELOPER", 999)
    bot = MagicMock()
    bot.send_message = AsyncMock()

    try:
        raise ValueError("boom")
    except ValueError as e:
        await error_reporting._notify_developer(bot, _make_event(e))

    bot.send_message.assert_awaited_once()
    chat_id, text = bot.send_message.call_args.args
    assert chat_id == 999
    assert "boom" in text
    assert "@alice" in text


@pytest.mark.asyncio
async def test_notify_developer_truncates_long_traceback(monkeypatch):
    monkeypatch.setattr(error_reporting, "DEVELOPER", 1)
    bot = MagicMock()
    bot.send_message = AsyncMock()

    try:
        raise RuntimeError("x" * 10000)
    except RuntimeError as e:
        await error_reporting._notify_developer(bot, _make_event(e))

    text = bot.send_message.call_args.args[1]
    # Под лимитом Telegram (4096) и с маркером усечения.
    assert len(text) < 4096
    assert "обрезано" in text


@pytest.mark.asyncio
async def test_notify_developer_swallows_send_failure(monkeypatch):
    """Сбой доставки не должен пробрасываться поверх исходной ошибки."""
    monkeypatch.setattr(error_reporting, "DEVELOPER", 1)
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("telegram down"))

    try:
        raise ValueError("boom")
    except ValueError as e:
        await error_reporting._notify_developer(bot, _make_event(e))  # must not raise


def _capture_handler(dp_errors_calls):
    """Фейковый dp.errors() — захватывает зарегистрированный хендлер."""

    def errors():
        def wrap(fn):
            dp_errors_calls["fn"] = fn
            return fn

        return wrap

    return errors


@pytest.mark.asyncio
async def test_error_handler_skips_when_developer_unset(monkeypatch):
    monkeypatch.setattr(error_reporting, "DEVELOPER", None)
    captured: dict = {}
    dp = MagicMock()
    dp.errors = _capture_handler(captured)

    error_reporting.register_error_handler(dp)

    bot = MagicMock()
    bot.send_message = AsyncMock()
    result = await captured["fn"](_make_event(ValueError("x")), bot)

    assert result is True
    bot.send_message.assert_not_awaited()
