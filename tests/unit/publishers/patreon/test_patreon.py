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
from sagenza_tgbot_sdk.resilience import PermanentError

HOME = '<script>window.patreon = {"csrfSignature": "sig-1"}</script>'
RULES = [
    {"type": "access-rule", "id": "r-patrons", "attributes": {"access_rule_type": "patrons"}},
    {
        "type": "access-rule",
        "id": "r-gold",
        "attributes": {"access_rule_type": "tier"},
        "relationships": {"tier": {"data": {"id": "t-gold", "type": "tier"}}},
    },
]


class FakePatreon:
    def __init__(self):
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if path == "/":
            return httpx.Response(200, text=HOME)
        if path == "/api/current_user":
            return httpx.Response(200, json={"data": {"relationships": {"campaign": {"data": {"id": "c1"}}}}})
        if path == "/api/campaigns/c1":
            return httpx.Response(200, json={"data": {"id": "c1"}, "included": RULES})
        if path == "/api/posts" and method == "POST":
            return httpx.Response(201, json={"data": {"id": "p1", "type": "post"}})
        if path == "/api/media":
            return httpx.Response(
                201,
                json={
                    "data": {
                        "id": "m1",
                        "attributes": {"upload_url": "https://s3.test/up", "upload_parameters": {"key": "k"}},
                    }
                },
            )
        if request.url.host == "s3.test":
            return httpx.Response(204)
        if path == "/api/posts/p1" and method == "PATCH":
            return httpx.Response(200, json={"data": {"id": "p1"}})
        if path == "/api/posts/p1":
            return httpx.Response(200, json={"data": {"id": "p1", "attributes": {"published_at": "2026-09-27"}}})
        return httpx.Response(404)


@pytest.fixture
def fake(monkeypatch):
    fake = FakePatreon()
    real = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(fake)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    return fake


def _client(tmp_path, tier_ids=None):
    session = tmp_path / "patreon_session.json"
    save_session(str(session), "sess-1", "UA")
    return PatreonClient(str(session), tier_ids or [])


@pytest.mark.asyncio
async def test_full_publish_flow(tmp_path, fake):
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"ID3")
    client = _client(tmp_path, ["t-gold"])

    rules = await client.access_rules()
    post_id = await client.create_draft()
    await client.upload_audio(post_id, str(mp3))
    await client.publish(post_id, title="T", content="<p>c</p>", teaser="c", rule_ids=rules)

    assert rules == ["r-gold"]
    assert await client.get_post(post_id) == {"id": "p1", "attributes": {"published_at": "2026-09-27"}}
    patch = next(r for r in fake.requests if r.method == "PATCH")
    body = json.loads(patch.content)
    assert body["data"]["attributes"]["title"] == "T"
    assert body["data"]["attributes"]["tags"] == {"publish": True}
    assert body["data"]["relationships"]["access_rules"]["data"] == [{"type": "access-rule", "id": "r-gold"}]
    assert patch.headers["X-CSRF-Signature"] == "sig-1"
    assert "session_id=sess-1" in patch.headers["cookie"]
    media = json.loads(next(r for r in fake.requests if r.url.path == "/api/media").content)
    assert media["data"]["attributes"]["owner_id"] == "p1"
    assert media["data"]["attributes"]["size_bytes"] == 3
    s3 = next(r for r in fake.requests if r.url.host == "s3.test")
    assert b'name="key"' in s3.content


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
    assert "<p>Описание</p>" in kwargs["content"]
    result = producer.send.await_args.args[1]
    assert result["status"] == "success"
    assert result["metadata"] == {"url": "https://www.patreon.com/posts/p1"}


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
