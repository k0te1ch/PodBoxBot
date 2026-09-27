"""Tests for BoostyClient — upload/publish/refresh against a fake transport.

Реальный Boosty не дёргаем: клиент получает фейковый Transport, который
отвечает заготовленными ответами и записывает запросы. Так проверяем сборку
payload, последовательность вызовов и обработку 401/refresh без сети.
"""

import json
import time

import pytest
from app.publishers.Boosty.boosty_client import BoostyApiError, BoostyClient, Response
from boosty_auth import AuthData, BoostyAuthError, load, save


class FakeTransport:
    """Отвечает по первому подходящему правилу (метод, суффикс URL)."""

    def __init__(self, rules):
        self.rules = [list(r) for r in rules]
        self.calls = []

    async def send(self, method, url, *, headers, data=None, json_body=None, params=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "data": data, "json": json_body})
        for rule in self.rules:
            rule_method, suffix, responses = rule
            if method == rule_method and url.endswith(suffix):
                resp = responses.pop(0) if len(responses) > 1 else responses[0]
                return resp
        raise AssertionError(f"unexpected request {method} {url}")


def ok(body=None, status=200):
    return Response(status, json.dumps(body or {}).encode())


@pytest.fixture
def auth_file(tmp_path):
    path = tmp_path / "boosty_auth.json"
    save(
        path,
        AuthData(
            access_token="old",
            refresh_token="r1",
            expires_at=int(time.time()) + 86400,
            device_id="dev",
        ),
    )
    return path


def make_client(auth_file, rules):
    transport = FakeTransport(rules)
    return BoostyClient("podbox", str(auth_file), transport=transport), transport


@pytest.mark.asyncio
async def test_get_container_id_parses_owner_id(auth_file):
    client, _ = make_client(auth_file, [("GET", "/post_draft", [ok({"data": {"postDraft": {"ownerId": 1900545}}})])])

    assert await client.get_container_id() == 1900545


@pytest.mark.asyncio
async def test_upload_audio_flow(tmp_path, auth_file):
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"x" * 100)
    client, transport = make_client(
        auth_file,
        [
            ("POST", "/audio", [ok({"fileId": "aud-1"})]),
            ("POST", "/upload/aud-1", [ok()]),
            ("POST", "/upload/aud-1/complete", [ok()]),
        ],
    )

    file_id, size = await client.upload_audio(str(mp3), 1900545)

    assert (file_id, size) == ("aud-1", 100)
    init = transport.calls[0]
    assert init["json"] == {"container_id": 1900545, "container_type": "post_draft"}
    assert init["headers"]["Authorization"] == "Bearer old"
    assert init["headers"]["X-App"] == "web"
    chunk = transport.calls[1]
    assert chunk["url"].endswith("/upload/aud-1")
    # чанк несёт X-PartNumber (1-based) — обязателен, иначе 400
    assert chunk["headers"]["X-PartNumber"] == "1"
    assert chunk["data"] == b"x" * 100
    assert transport.calls[2]["url"].endswith("/upload/aud-1/complete")


@pytest.mark.asyncio
async def test_upload_image_init_has_empty_body(tmp_path, auth_file):
    img = tmp_path / "cover.png"
    img.write_bytes(b"\x89PNG" + b"0" * 50)
    client, transport = make_client(
        auth_file,
        [
            ("POST", "/image", [ok({"fileId": "img-1"})]),
            ("POST", "/upload/img-1", [ok()]),
            ("POST", "/complete", [ok()]),
        ],
    )

    assert await client.upload_image(str(img)) == "img-1"
    assert transport.calls[0]["url"].endswith("/image")
    assert transport.calls[0]["json"] == {}


@pytest.mark.asyncio
async def test_publish_assembles_payload(auth_file):
    client, transport = make_client(
        auth_file,
        [
            ("PUT", "/v1/blog/podbox/post_draft", [ok({"data": {}})]),
            ("POST", "/post_draft/publish/", [ok({"data": {"post": {"id": "post-9", "int_id": 123}}})]),
        ],
    )

    post_id = await client.publish(
        title="751. Послешоу",
        body="описание\nвторой абзац",
        chapters=[["00:00", "Intro"]],
        audio_id="aud-1",
        audio_size=555,
        audio_title="ep.mp3",
        cover_id="img-1",
        subscription_level_id="407063",
        price=10,
        advertiser_info="",
    )

    assert post_id == "post-9"
    put, pub = transport.calls
    assert put["method"] == "PUT"
    payload = put["data"]
    assert payload["title"] == "751. Послешоу"
    assert payload["subscription_level_id"] == "407063"
    assert payload["price"] == "10"
    data = json.loads(payload["data"])
    assert any(b.get("type") == "audio_file" and b["id"] == "aud-1" for b in data)
    teaser = json.loads(payload["teaser_data"])
    assert teaser[0]["type"] == "image"
    assert teaser[0]["id"] == "img-1"
    assert pub["data"] == {"is_showcase_visible": "true"}


@pytest.mark.asyncio
async def test_401_refreshes_once_and_retries(auth_file):
    client, transport = make_client(
        auth_file,
        [
            ("GET", "/post/p1", [Response(401, b"{}"), ok({"id": "p1"})]),
            ("POST", "/oauth/token/", [ok({"access_token": "new", "refresh_token": "r2", "expires_in": 3600})]),
        ],
    )

    assert await client.get_post("p1") == {"id": "p1"}

    refresh = transport.calls[1]
    assert refresh["data"]["grant_type"] == "refresh_token"
    assert refresh["data"]["refresh_token"] == "r1"
    assert refresh["data"]["device_id"] == "dev"
    assert "Authorization" not in refresh["headers"]
    assert transport.calls[2]["headers"]["Authorization"] == "Bearer new"
    saved = load(auth_file)
    assert (saved.access_token, saved.refresh_token) == ("new", "r2")


@pytest.mark.asyncio
async def test_rejected_refresh_raises_auth_error(auth_file):
    client, _ = make_client(
        auth_file,
        [
            ("GET", "/post/p1", [Response(401, b"{}")]),
            ("POST", "/oauth/token/", [Response(400, b'{"error":"invalid_grant"}')]),
        ],
    )

    with pytest.raises(BoostyAuthError, match="boosty_auth.json"):
        await client.get_post("p1")


@pytest.mark.asyncio
async def test_401_after_refresh_raises_auth_error(auth_file):
    client, transport = make_client(
        auth_file,
        [
            ("GET", "/post/p1", [Response(401, b"{}")]),
            ("POST", "/oauth/token/", [ok({"access_token": "new", "expires_in": 3600})]),
        ],
    )

    with pytest.raises(BoostyAuthError, match="после refresh"):
        await client.get_post("p1")
    assert len(transport.calls) == 3


@pytest.mark.asyncio
async def test_token_close_to_expiry_is_refreshed_first(tmp_path):
    path = tmp_path / "a.json"
    save(path, AuthData(access_token="old", refresh_token="r1", expires_at=int(time.time()) + 60, device_id="d"))
    client, transport = make_client(
        path,
        [
            ("POST", "/oauth/token/", [ok({"access_token": "new", "expires_in": 3600})]),
            ("GET", "/post/p1", [ok({"id": "p1"})]),
        ],
    )

    await client.get_post("p1")

    assert transport.calls[0]["url"].endswith("/oauth/token/")
    assert transport.calls[1]["headers"]["Authorization"] == "Bearer new"


@pytest.mark.asyncio
async def test_server_error_is_retryable_api_error(auth_file):
    client, _ = make_client(auth_file, [("GET", "/post/p1", [Response(502, b"<html>")])])

    with pytest.raises(BoostyApiError) as exc:
        await client.get_post("p1")
    assert not isinstance(exc.value, BoostyAuthError)
    assert exc.value.status == 502


@pytest.mark.asyncio
async def test_missing_auth_file_is_auth_error(tmp_path):
    client, _ = make_client(tmp_path / "nope.json", [])

    with pytest.raises(BoostyAuthError, match="нет файла"):
        await client.ensure_auth()


@pytest.mark.asyncio
async def test_empty_blog_is_auth_error(auth_file):
    client = BoostyClient("", str(auth_file), transport=FakeTransport([]))

    with pytest.raises(BoostyAuthError, match="BOOSTY_BLOG"):
        await client.ensure_auth()


def test_auth_from_browser_cookies():
    cookie = "%7B%22accessToken%22%3A%22a%22%2C%22refreshToken%22%3A%22r%22%2C%22expiresAt%22%3A1790000000000%7D"

    data = AuthData.from_cookies(cookie, " client-1 ")

    assert (data.access_token, data.refresh_token, data.device_id) == ("a", "r", "client-1")
    assert data.expires_at == 1790000000  # миллисекунды куки → секунды


def test_auth_from_cookies_requires_tokens():
    with pytest.raises(ValueError, match="accessToken"):
        AuthData.from_cookies("%7B%7D", "c")


def test_legacy_auth_file_is_readable(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(
        json.dumps(
            {
                "access_token": "a",
                "refresh_token": "r",
                "expires_at": "1790000000",
                "device_id": "d",
                "user_agent": None,
            }
        ),
        encoding="utf-8",
    )

    data = load(path)

    assert data.expires_at == 1790000000
    assert data.user_agent is None
