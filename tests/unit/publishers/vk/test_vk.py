"""VK publisher: клиент VK API на httpx.MockTransport и Kafka-хендлер на моках."""

from unittest.mock import AsyncMock

import httpx
import pytest
from app.publishers.VK import vk_client
from app.publishers.VK.vk_client import VkApiError, VkAuthError, VkClient


def _client(handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return VkClient("token", 123, "5.199", http=http)


def _form(request: httpx.Request) -> dict:
    return dict(httpx.QueryParams(request.content.decode()))


@pytest.mark.asyncio
async def test_post_is_donut_only_on_group_wall():
    seen = {}

    def handler(request):
        seen.update(_form(request))
        return httpx.Response(200, json={"response": {"post_id": 77}})

    client = _client(handler)

    assert await client.post("текст", ["video-123_5"], -1) == "77"
    assert seen["owner_id"] == "-123"
    assert seen["from_group"] == "1"
    assert seen["donut_paid_duration"] == "-1"
    assert seen["attachments"] == "video-123_5"
    assert seen["access_token"] == "token"
    assert seen["v"] == "5.199"


@pytest.mark.asyncio
async def test_doc_upload_flow(tmp_path):
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"ID3")
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("docs.getWallUploadServer"):
            assert _form(request)["group_id"] == "123"
            return httpx.Response(200, json={"response": {"upload_url": "https://pu.vk.com/up"}})
        if request.url.host == "pu.vk.com":
            assert b'name="file"' in request.content
            return httpx.Response(200, json={"file": "blob"})
        assert _form(request)["file"] == "blob"
        return httpx.Response(200, json={"response": {"type": "doc", "doc": {"id": 9, "owner_id": -123}}})

    client = _client(handler)

    assert await client.upload_doc(str(mp3), "ep.mp3") == "doc-123_9"
    assert calls[-1].endswith("docs.save")


@pytest.mark.asyncio
async def test_video_upload_converts_and_saves(tmp_path, monkeypatch):
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"ID3")

    async def fake_ffmpeg(_mp3, _cover, out):
        with open(out, "wb") as f:
            f.write(b"mp4")

    monkeypatch.setattr(vk_client, "mp3_to_video", fake_ffmpeg)

    def handler(request):
        if request.url.path.endswith("video.save"):
            form = _form(request)
            assert form["group_id"] == "123"
            assert form["wallpost"] == "0"
            return httpx.Response(
                200, json={"response": {"upload_url": "https://vu.vk.com/up", "video_id": 5, "owner_id": -123}}
            )
        assert b'name="video_file"' in request.content
        return httpx.Response(200, json={"video_hash": "h"})

    client = _client(handler)

    assert await client.upload_video(str(mp3), "cover.jpg", "t", "d") == "video-123_5"


@pytest.mark.asyncio
@pytest.mark.parametrize(("code", "exc"), [(5, VkAuthError), (15, VkAuthError), (6, VkApiError)])
async def test_errors_are_classified(code, exc):
    client = _client(lambda r: httpx.Response(200, json={"error": {"error_code": code, "error_msg": "x"}}))

    with pytest.raises(exc) as info:
        await client.call("wall.post")
    if code == 6:
        assert not isinstance(info.value, VkAuthError)


def test_missing_token_is_auth_error():
    with pytest.raises(VkAuthError, match="VK_ACCESS_TOKEN"):
        VkClient(None, 1, "5.199").check_config()


@pytest.fixture
def publisher(monkeypatch):
    from app.publishers.VK import main

    client = AsyncMock()
    client.check_config = lambda: None
    client.upload_video = AsyncMock(return_value="video-123_5")
    client.upload_doc = AsyncMock(return_value="doc-123_9")
    client.post = AsyncMock(return_value="77")
    client.get_post = AsyncMock(return_value={"id": 77})
    client.post_url = lambda pid: f"https://vk.com/wall-123_{pid}"
    monkeypatch.setattr(main._publisher, "client", client)
    monkeypatch.setattr(main._publisher, "media", "video")
    return main, client


@pytest.mark.asyncio
async def test_handler_publishes_and_reports_url(event_dict, publisher):
    main, client = publisher
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    message, attachments, duration = client.post.await_args.args
    assert message.startswith("42. Послешоу")
    assert "00:00 — Начало" in message
    assert attachments == ["video-123_5"]
    assert duration == -1
    result = producer.send.await_args.args[1]
    assert result["status"] == "success"
    assert result["post_id"] == "77"
    assert result["metadata"] == {"url": "https://vk.com/wall-123_77"}


@pytest.mark.asyncio
async def test_doc_mode_attaches_document(event_dict, publisher, monkeypatch):
    main, client = publisher
    monkeypatch.setattr(main._publisher, "media", "doc")

    await main.handle_upload(event_dict, AsyncMock())

    client.upload_video.assert_not_awaited()
    assert client.post.await_args.args[1] == ["doc-123_9"]


@pytest.mark.asyncio
async def test_auth_error_fails_without_retry(event_dict, publisher):
    main, client = publisher
    client.upload_video = AsyncMock(side_effect=VkAuthError("video.save", 5, "invalid token"))
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    client.upload_video.assert_awaited_once()
    result = producer.send.await_args.args[1]
    assert result["status"] == "failure"
    assert "VK_ACCESS_TOKEN" in result["error"]


@pytest.mark.asyncio
async def test_missing_post_fails_verify(event_dict, publisher):
    main, client = publisher
    client.get_post = AsyncMock(return_value=None)
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    result = producer.send.await_args.args[1]
    assert result["status"] == "failure"
    assert result["metadata"]["stage"] == "verify"
