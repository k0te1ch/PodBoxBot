"""Patreon publisher: клиент веб-редактора на httpx.MockTransport и хендлер на моках."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from app.publishers.Patreon.patreon_client import (
    PatreonAuthError,
    PatreonClient,
    load_session,
    pick_access_rules,
    save_session,
)
from sagenza_tgbot_sdk.masking import default_masker, mask_secrets
from sagenza_tgbot_sdk.resilience import PermanentError

RULES = [
    {"type": "access-rule", "id": "r-public", "attributes": {"access_rule_type": "public"}},
    {"type": "access-rule", "id": "r-patrons", "attributes": {"access_rule_type": "patrons"}},
    {
        "type": "access-rule",
        "id": "r-gold",
        "attributes": {"access_rule_type": "tier"},
        "relationships": {"tier": {"data": {"id": "t-gold", "type": "reward"}}},
    },
]


class FakePatreon:
    """Обезличенный patreon.com: пути, поля и ответы как в записи редактора."""

    def __init__(self):
        self.requests = []
        self.media_polls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if path == "/REST/auth/CSRFTicket":
            return httpx.Response(200, json={"token": "sig-1", "time": "1", "URI": "/"})
        if path == "/api/current_user":
            return httpx.Response(200, json={"data": {"relationships": {"campaign": {"data": {"id": "c1"}}}}})
        if path == "/api/campaigns/c1":
            return httpx.Response(200, json={"data": {"id": "c1"}, "included": RULES})
        if path == "/api/posts/new" and method == "POST":
            return httpx.Response(200, json={"data": {"id": "p1", "type": "post", "attributes": {"edit_url": "/e"}}})
        if path == "/api/media" and method == "POST":
            return httpx.Response(
                201,
                json={
                    "data": {
                        "id": "m1",
                        "type": "media",
                        "attributes": {
                            "state": "pending_upload",
                            "upload_url": "https://s3.test/",
                            "upload_parameters": {"key": "k", "acl": "authenticated-read", "policy": "p"},
                        },
                    }
                },
            )
        if request.url.host == "s3.test":
            return httpx.Response(204)
        if path == "/api/media/m1":
            self.media_polls += 1
            state = "ready" if self.media_polls > 1 else "processing"
            return httpx.Response(200, json={"data": {"id": "m1", "attributes": {"state": state}}})
        if path == "/api/posts/p1" and method == "PATCH":
            return httpx.Response(
                200, json={"data": {"id": "p1", "attributes": {"url": "https://www.patreon.com/posts/ep-p1"}}}
            )
        if path == "/api/posts/p1":
            return httpx.Response(200, json={"data": {"id": "p1", "attributes": {"published_at": "2026-09-27"}}})
        return httpx.Response(404)


def _patch_transport(monkeypatch, handler):
    real = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)


@pytest.fixture
def fake(monkeypatch):
    fake = FakePatreon()
    _patch_transport(monkeypatch, fake)
    return fake


def _client(tmp_path, tier_ids=None):
    session = tmp_path / "patreon_session.json"
    save_session(str(session), "sess-1", "UA")
    return PatreonClient(str(session), tier_ids or [], media_poll_delay=0)


@pytest.mark.asyncio
async def test_full_publish_flow(tmp_path, fake):
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"ID3")
    client = _client(tmp_path, ["t-gold"])

    rules = await client.access_rules()
    post_id = await client.create_draft()
    media_id = await client.upload_audio(post_id, str(mp3))
    url = await client.publish(post_id, title="T", lines=["строка <1>", "00:00 — Начало"], rule_ids=rules)

    assert rules == ["r-gold"]
    assert media_id == "m1"
    assert fake.media_polls == 2
    assert url == "https://www.patreon.com/posts/ep-p1"
    assert await client.get_post(post_id) == {"id": "p1", "attributes": {"published_at": "2026-09-27"}}

    draft = next(r for r in fake.requests if r.url.path == "/api/posts/new")
    assert json.loads(draft.content)["data"]["attributes"] == {"post_type": "text_only", "post_visibility": "paid"}
    assert draft.url.params["json-api-version"] == "1.0"

    media = json.loads(next(r for r in fake.requests if r.url.path == "/api/media").content)["data"]["attributes"]
    assert media["owner_id"] == "p1"
    assert media["owner_type"] == "post"
    assert media["owner_relationship"] == "audio"
    assert media["media_type"] == "audio"
    assert media["state"] == "pending_upload"
    assert media["size_bytes"] == 3
    s3 = next(r for r in fake.requests if r.url.host == "s3.test")
    assert b'name="key"' in s3.content
    assert b'name="file"' in s3.content
    assert "cookie" not in s3.headers

    patch = next(r for r in fake.requests if r.method == "PATCH")
    body = json.loads(patch.content)
    attrs = body["data"]["attributes"]
    assert attrs["title"] == "T"
    assert attrs["post_type"] == "podcast"
    assert attrs["tags"] == {"publish": True}
    assert attrs["content"] == "<p>строка &lt;1&gt;</p><p>00:00 — Начало</p>"
    doc = json.loads(attrs["content_json_string"])
    assert doc["content"][0]["type"] == "paywallBreakpoint"
    assert [n["content"][0]["text"] for n in doc["content"][1:]] == ["строка <1>", "00:00 — Начало"]
    assert body["data"]["relationships"]["access_rules"]["data"] == [{"type": "access-rule", "id": "r-gold"}]
    assert body["data"]["relationships"]["access-rule"]["data"] == {"type": "access-rule", "id": "r-gold"}
    assert body["meta"] == {"auto_save": False, "send_notifications": True}
    assert patch.headers["X-CSRF-Signature"] == "sig-1"
    assert "session_id=sess-1" in patch.headers["cookie"]
    campaign = next(r for r in fake.requests if r.url.path == "/api/campaigns/c1")
    assert campaign.url.params["include"] == "access_rules.tier.null"


@pytest.mark.asyncio
async def test_failed_media_is_permanent(tmp_path, monkeypatch):
    fake = FakePatreon()

    def handler(request):
        if request.url.path == "/api/media/m1":
            return httpx.Response(200, json={"data": {"id": "m1", "attributes": {"state": "failed"}}})
        return fake(request)

    _patch_transport(monkeypatch, handler)
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"ID3")

    with pytest.raises(PermanentError, match="failed"):
        await _client(tmp_path).upload_audio("p1", str(mp3))


@pytest.mark.asyncio
async def test_missing_csrf_ticket_is_auth_error(tmp_path, monkeypatch):
    _patch_transport(monkeypatch, lambda r: httpx.Response(200, json={}))

    with pytest.raises(PatreonAuthError, match="CSRFTicket"):
        await _client(tmp_path).create_draft()


def test_default_rule_is_all_patrons():
    assert pick_access_rules(RULES, []) == ["r-patrons"]


def test_unknown_tier_is_permanent_error():
    with pytest.raises(PermanentError, match="PATREON_TIER_IDS"):
        pick_access_rules(RULES, ["nope"])


@pytest.mark.asyncio
async def test_rejected_session_is_auth_error(tmp_path, monkeypatch):
    real = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(lambda r: httpx.Response(401))
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)

    with pytest.raises(PatreonAuthError, match="patreon_session.json"):
        await _client(tmp_path).ensure_auth()


def test_missing_session_file(tmp_path):
    with pytest.raises(PatreonAuthError, match="нет файла"):
        load_session(str(tmp_path / "nope.json"))


@pytest.fixture
def publisher(monkeypatch):
    from app.publishers.Patreon import main

    client = AsyncMock()
    client.access_rules = AsyncMock(return_value=["r-patrons"])
    client.create_draft = AsyncMock(return_value="p1")
    client.publish = AsyncMock(return_value=None)
    client.get_post = AsyncMock(return_value={"id": "p1"})
    client.post_url = lambda pid: f"https://www.patreon.com/posts/{pid}"
    monkeypatch.setattr(main._publisher, "client", client)
    return main, client


@pytest.mark.asyncio
async def test_handler_publishes(event_dict, publisher):
    main, client = publisher
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    client.upload_audio.assert_awaited_once_with("p1", "/app/files/0042_postshow.mp3")
    kwargs = client.publish.await_args.kwargs
    assert kwargs["rule_ids"] == ["r-patrons"]
    assert kwargs["lines"] == ["Описание", "00:00 — Начало"]
    result = producer.send.await_args.args[1]
    assert result["status"] == "success"
    assert result["metadata"] == {
        "platform": "patreon",
        "action": "published",
        "url": "https://www.patreon.com/posts/p1",
    }


@pytest.mark.asyncio
async def test_handler_auth_error_is_reported(event_dict, publisher):
    main, client = publisher
    client.ensure_auth = AsyncMock(side_effect=PatreonAuthError("сессия не принята"))
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    client.create_draft.assert_not_awaited()
    result = producer.send.await_args.args[1]
    assert result["status"] == "failure"
    assert "import-cookie" in result["error"]


def test_session_cookie_from_the_file_is_masked(tmp_path):
    """Кука сессии вырезается из логов и текста ошибок."""
    path = str(tmp_path / "patreon_session.json")
    save_session(path, "patreon-session-value", "UA")
    try:
        load_session(path)

        text = mask_secrets("HTTP 403: session patreon-session-value rejected")
    finally:
        default_masker.clear()

    assert text == "HTTP 403: session *** rejected"
