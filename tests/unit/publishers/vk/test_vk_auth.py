"""VK ID auth: refresh, ротация пары, обмен кода, срок жизни — на httpx.MockTransport."""

import json
import time

import httpx
import pytest
from app.publishers.VK import vk_auth
from app.publishers.VK.vk_auth import REFRESH_TOKEN_TTL, VkAuth, VkAuthData, VkAuthError


def _auth(handler, auth_file):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return VkAuth(client_id=42, auth_file=str(auth_file), http=http)


def _write(auth_file, **kw):
    base = {
        "access_token": "old_a",
        "refresh_token": "old_r",
        "device_id": "dev1",
        "expires_at": 0,
    }
    base.update(kw)
    auth_file.write_text(json.dumps(base), encoding="utf-8")
    return auth_file


def test_pkce_pair_is_url_safe_and_derived():
    verifier, challenge = vk_auth.make_pkce()
    assert verifier and challenge
    assert "=" not in challenge and "+" not in challenge and "/" not in challenge
    # challenge детерминированно выводится из verifier (S256)
    import base64
    import hashlib

    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected


def test_authorize_url_has_pkce_and_scope():
    url = vk_auth.authorize_url(42, "https://cb", "chal", "st", "wall video")
    assert url.startswith("https://id.vk.ru/authorize?")
    assert "code_challenge=chal" in url and "code_challenge_method=S256" in url
    assert "client_id=42" in url and "scope=wall+video" in url


@pytest.mark.asyncio
async def test_refresh_rotates_and_persists(tmp_path):
    auth_file = _write(tmp_path / "vk.json", expires_at=int(time.time()))  # истёк → обновится
    seen = {}

    def handler(request):
        seen.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(
            200,
            json={
                "access_token": "new_a",
                "refresh_token": "new_r",
                "expires_in": 3600,
            },
        )

    auth = _auth(handler, auth_file)
    token = await auth.access_token()

    assert token == "new_a"
    assert seen["grant_type"] == "refresh_token"
    assert seen["refresh_token"] == "old_r"
    assert seen["device_id"] == "dev1"
    assert seen["client_id"] == "42"
    # новая пара записана на диск, старый refresh больше не хранится
    saved = json.loads(auth_file.read_text(encoding="utf-8"))
    assert saved["access_token"] == "new_a"
    assert saved["refresh_token"] == "new_r"
    assert saved["refresh_expires_at"] >= int(time.time()) + REFRESH_TOKEN_TTL - 5


@pytest.mark.asyncio
async def test_valid_access_token_is_not_refreshed(tmp_path):
    auth_file = _write(tmp_path / "vk.json", access_token="live_a", expires_at=int(time.time()) + 3600)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"access_token": "x", "expires_in": 3600})

    auth = _auth(handler, auth_file)
    assert await auth.access_token() == "live_a"
    assert calls == []  # запроса к VK ID не было


@pytest.mark.asyncio
async def test_rejected_refresh_raises_auth_error(tmp_path):
    auth_file = _write(tmp_path / "vk.json", expires_at=0)

    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "expired"})

    auth = _auth(handler, auth_file)
    with pytest.raises(VkAuthError) as info:
        await auth.access_token()
    assert "SMOKE.md" in str(info.value)  # подсказка «как починить» на месте


@pytest.mark.asyncio
async def test_exchange_code_writes_first_pair(tmp_path):
    auth_file = tmp_path / "vk.json"
    seen = {}

    def handler(request):
        seen.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(
            200,
            json={
                "access_token": "a1",
                "refresh_token": "r1",
                "expires_in": 3600,
                "user_id": 7,
            },
        )

    auth = _auth(handler, auth_file)
    data = await auth.exchange_code("the_code", "dev9", "verifier9", state="st")

    assert seen["grant_type"] == "authorization_code"
    assert seen["code"] == "the_code" and seen["code_verifier"] == "verifier9"
    assert seen["device_id"] == "dev9"
    assert data.refresh_token == "r1" and data.user_id == 7
    assert auth_file.exists()


def test_missing_refresh_token_in_file_is_auth_error(tmp_path):
    bad = tmp_path / "vk.json"
    bad.write_text(json.dumps({"access_token": "a"}), encoding="utf-8")
    with pytest.raises(VkAuthError, match="refresh_token"):
        vk_auth.load(bad)


def test_refresh_seconds_left_and_expiry_flags():
    now = 1_000_000
    ten_days = 10 * 24 * 3600
    data = VkAuthData(refresh_expires_at=now + ten_days, expires_at=now + 100)
    assert data.refresh_seconds_left(now=now) == ten_days
    assert not data.access_expires_soon(now=now - 1000)
    assert data.access_expires_soon(now=now + 50)  # внутри REFRESH_MARGIN


def test_safe_hides_tokens_but_shows_error():
    out = vk_auth._safe({"access_token": "secret", "error": "invalid_grant", "state": "st"})
    assert "secret" not in out
    assert "invalid_grant" in out
