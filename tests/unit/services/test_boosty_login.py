"""Вход в Boosty через бота: разбор присланных кук, файл токенов, ответы админу."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

import pytest
from aiogram.enums import ChatType
from fakeredis import FakeAsyncRedis

from handlers import boosty_login_handler as handler
from services import boosty_session
from services.i18n import t
from shared.boosty_cookies import SNIPPET, CookieError, looks_like_cookies, parse

AUTH = quote(json.dumps({"accessToken": "acc", "refreshToken": "ref", "expiresAt": 1_900_000_000_000}))
SNIPPET_LINE = "PODBOX-BOOSTY " + json.dumps({"auth": AUTH, "clientId": "dev-1", "ua": "Mozilla/5.0"})


@pytest.mark.parametrize(
    "text",
    [
        SNIPPET_LINE,
        f"Cookie: last_acc=1; auth={AUTH}; _clientId=dev-1",
        json.dumps([{"name": "auth", "value": AUTH}, {"name": "_clientId", "value": "dev-1"}]),
    ],
)
def test_every_supported_form_gives_the_same_login(text):
    assert looks_like_cookies(text)
    login = parse(text)
    assert (login.client_id, boosty_session.auth_file_data(login)["refresh_token"]) == ("dev-1", "ref")


def test_ordinary_text_is_not_taken_for_cookies():
    assert not looks_like_cookies("привет, как дела с выпуском?")


def test_cookie_without_tokens_is_explained():
    with pytest.raises(CookieError, match="accessToken"):
        boosty_session.auth_file_data(parse("auth=%7B%7D; _clientId=dev-1"))


def test_snippet_reads_both_cookies():
    assert "auth=" in SNIPPET and "_clientId=" in SNIPPET and "PODBOX-BOOSTY" in SNIPPET


def test_login_is_written_in_the_publisher_format(tmp_path):
    path = tmp_path / "boosty_auth.json"

    boosty_session.save_login(SNIPPET_LINE, str(path))

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == {
        "access_token": "acc",
        "refresh_token": "ref",
        "expires_at": 1_900_000_000,
        "device_id": "dev-1",
        "user_agent": "Mozilla/5.0",
    }
    assert not (tmp_path / "boosty_auth.json.tmp").exists()


def _admin_message(text):
    msg = MagicMock()
    msg.text = text
    msg.chat.type = ChatType.PRIVATE
    msg.from_user.id = 1
    msg.from_user.language_code = "ru"
    msg.delete = AsyncMock()
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def redis(monkeypatch):
    fake = FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(handler, "redis", fake)
    return fake


@pytest.fixture
def auth_file(tmp_path, monkeypatch):
    import config

    path = tmp_path / "boosty_auth.json"
    monkeypatch.setattr(config, "BOOSTY_AUTH_FILE", str(path))
    monkeypatch.setattr(config, "BOOSTY_BLOG", "podbox")
    return path


@pytest.mark.asyncio
async def test_cookies_are_deleted_saved_and_checked(redis, auth_file):
    await redis.set(boosty_session.DOWN_KEY, "1")
    msg = _admin_message(SNIPPET_LINE)

    with patch.object(handler, "verify_login", AsyncMock(return_value=True)) as verify:
        await handler.receive_cookies(msg)

    msg.delete.assert_awaited_once()
    assert json.loads(auth_file.read_text(encoding="utf-8"))["device_id"] == "dev-1"
    verify.assert_awaited_once()
    msg.answer.assert_awaited_once_with(t("boosty_login_saved", blog="podbox"))
    assert await redis.get(boosty_session.DOWN_KEY) is None


@pytest.mark.asyncio
async def test_rejected_cookies_are_reported(redis, auth_file):
    msg = _admin_message(SNIPPET_LINE)

    with patch.object(handler, "verify_login", AsyncMock(return_value=False)):
        await handler.receive_cookies(msg)

    msg.answer.assert_awaited_once_with(t("boosty_login_rejected"))


@pytest.mark.asyncio
async def test_broken_cookies_are_deleted_and_explained(redis, auth_file):
    msg = _admin_message("auth=%7B%7D; _clientId=dev-1")

    await handler.receive_cookies(msg)

    msg.delete.assert_awaited_once()
    assert not auth_file.exists()
    assert "accessToken" in msg.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_lost_login_alert_offers_the_login_button():
    bot = MagicMock(send_message=AsyncMock())
    redis = FakeAsyncRedis(decode_responses=True)

    await boosty_session.on_session_event({"status": "failure", "error": "x"}, bot, redis, [1], "ru")

    markup = bot.send_message.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == boosty_session.LOGIN_CALLBACK
