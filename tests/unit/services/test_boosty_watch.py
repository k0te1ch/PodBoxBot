"""Периодическая проверка входа Boosty из бота (watchdog)."""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fakeredis import FakeAsyncRedis

from services import boosty_session

AUTH_FILE = "/app/data/boosty_auth.json"
BLOG = "podbox"


def _write_auth(path, expires_at=None, access_token="acc"):
    data = {"access_token": access_token, "refresh_token": "ref", "device_id": "dev-1"}
    if expires_at is not None:
        data["expires_at"] = expires_at
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


@pytest.fixture
def redis():
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def bot():
    return MagicMock(send_message=AsyncMock())


@pytest.mark.asyncio
async def test_missing_file_notifies_admins_once(bot, redis, tmp_path):
    path = str(tmp_path / "nope.json")
    await boosty_session.watch_tick(bot, redis, [1], "ru", path, BLOG)
    await boosty_session.watch_tick(bot, redis, [1], "ru", path, BLOG)

    # Флаг DOWN_KEY глушит повторы: одно сообщение на поломку.
    bot.send_message.assert_awaited_once()
    assert "не найден" in bot.send_message.await_args.args[1]


@pytest.mark.asyncio
async def test_broken_file_notifies_with_reason(bot, redis, tmp_path):
    path = tmp_path / "boosty_auth.json"
    path.write_text('{"access_token": "cut', encoding="utf-8")
    events = []
    with patch.object(boosty_session, "on_session_event", AsyncMock(side_effect=lambda *a: events.append(a[0]))):
        await boosty_session.watch_tick(bot, redis, [1], "ru", str(path), BLOG)

    assert events[0]["status"] == "failure"
    assert "повреждён" in events[0]["error"]


@pytest.mark.asyncio
async def test_expired_token_is_left_to_the_publisher(bot, redis, tmp_path):
    """Истёкший access_token бот не проверяет по сети: refresh — работа паблишера."""
    path = tmp_path / "boosty_auth.json"
    _write_auth(path, expires_at=int(time.time()) - 60)
    with (
        patch.object(boosty_session, "verify_login", AsyncMock()) as verify,
        patch.object(boosty_session, "on_session_event", AsyncMock()) as event,
    ):
        await boosty_session.watch_tick(bot, redis, [1], "ru", str(path), BLOG)

    verify.assert_not_awaited()
    event.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_login_reports_restore_after_outage(bot, redis, tmp_path):
    path = tmp_path / "boosty_auth.json"
    _write_auth(path, expires_at=int(time.time()) + 3600)
    await redis.set(boosty_session.DOWN_KEY, "1")
    with patch.object(boosty_session, "verify_login", AsyncMock(return_value=True)):
        await boosty_session.watch_tick(bot, redis, [1], "ru", str(path), BLOG)

    # Восстановление ушло, флаг поломки снят
    assert await redis.get(boosty_session.DOWN_KEY) is None
    bot.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_rejected_token_notifies_admins(bot, redis, tmp_path):
    path = tmp_path / "boosty_auth.json"
    _write_auth(path, expires_at=int(time.time()) + 3600)
    with (
        patch.object(boosty_session, "verify_login", AsyncMock(return_value=False)),
        patch.object(boosty_session, "on_session_event", AsyncMock()) as event,
    ):
        await boosty_session.watch_tick(bot, redis, [1], "ru", str(path), BLOG)

    event.assert_awaited_once()
    assert event.await_args.args[0]["status"] == "failure"


@pytest.mark.asyncio
async def test_recheck_after_file_rewrite_avoids_false_alarm(bot, redis, tmp_path):
    """401 пришёл, но файл уже переписали (паблишер обновил токен): проверяем заново."""
    path = tmp_path / "boosty_auth.json"
    _write_auth(path, expires_at=int(time.time()) + 3600)
    rewritten = False

    async def verify(data, blog):
        nonlocal rewritten
        if not rewritten:
            rewritten = True
            _write_auth(path, expires_at=int(time.time()) + 7200, access_token="fresh")
            return False
        return True

    with (
        patch.object(boosty_session, "verify_login", AsyncMock(side_effect=verify)),
        patch.object(boosty_session, "on_session_event", AsyncMock()) as event,
    ):
        await boosty_session.watch_tick(bot, redis, [1], "ru", str(path), BLOG)

    event.assert_awaited_once()
    assert event.await_args.args[0]["status"] == "success"


@pytest.mark.asyncio
async def test_network_trouble_stays_silent(bot, redis, tmp_path):
    path = tmp_path / "boosty_auth.json"
    _write_auth(path, expires_at=int(time.time()) + 3600)
    with (
        patch.object(boosty_session, "verify_login", AsyncMock(return_value=None)),
        patch.object(boosty_session, "on_session_event", AsyncMock()) as event,
    ):
        await boosty_session.watch_tick(bot, redis, [1], "ru", str(path), BLOG)

    event.assert_not_awaited()
