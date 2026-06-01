"""Tests for BoostyClient — upload/publish flow against a mocked lib HTTP client.

Реальный Boosty не дёргаем: подменяем `client._api` (объект либы) фейком с
http_client.request_json / request_raw / request и auth.headers. Так проверяем
сборку payload и последовательность вызовов, не выходя в сеть.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.publishers.Boosty.boosty_client import BoostyClient


def _fake_api(request_json_ret: dict, request_ret: dict | None = None):
    api = MagicMock()
    api.auth.headers = {"User-Agent": "ua", "Authorization": "Bearer t"}
    api.http_client.request_json = AsyncMock(return_value=request_json_ret)
    api.http_client.request_raw = AsyncMock(return_value=MagicMock(status=204))
    api.request = AsyncMock(return_value=request_ret if request_ret is not None else {})
    return api


@pytest.mark.asyncio
async def test_get_container_id_parses_owner_id():
    client = BoostyClient("podbox", "auth.json")
    client._api = _fake_api({}, request_ret={"data": {"postDraft": {"ownerId": 1900545}}})

    assert await client.get_container_id() == 1900545


@pytest.mark.asyncio
async def test_upload_audio_flow(tmp_path):
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"x" * 100)

    client = BoostyClient("podbox", "auth.json")
    client._api = _fake_api({"fileId": "aud-1"})

    file_id, size = await client.upload_audio(str(mp3), 1900545)

    assert file_id == "aud-1"
    assert size == 100

    init = client._api.http_client.request_json.await_args
    assert init.args[0].endswith("/audio")
    assert init.kwargs["json"] == {"container_id": 1900545, "container_type": "post_draft"}
    assert init.kwargs["headers"]["Authorization"] == "Bearer t"
    assert init.kwargs["headers"]["X-App"] == "web"

    raw_calls = client._api.http_client.request_raw.await_args_list
    raw_urls = [c.args[0] for c in raw_calls]
    assert any(u.endswith("/upload/aud-1") for u in raw_urls)
    assert any(u.endswith("/upload/aud-1/complete") for u in raw_urls)
    # чанк несёт X-PartNumber (1-based) — обязателен, иначе 400
    chunk_call = next(c for c in raw_calls if c.args[0].endswith("/upload/aud-1"))
    assert chunk_call.kwargs["headers"]["X-PartNumber"] == "1"


@pytest.mark.asyncio
async def test_upload_image_init_has_empty_body(tmp_path):
    img = tmp_path / "cover.png"
    img.write_bytes(b"\x89PNG" + b"0" * 50)

    client = BoostyClient("podbox", "auth.json")
    client._api = _fake_api({"fileId": "img-1"})

    assert await client.upload_image(str(img)) == "img-1"
    init = client._api.http_client.request_json.await_args
    assert init.args[0].endswith("/image")
    assert init.kwargs["json"] == {}


@pytest.mark.asyncio
async def test_publish_assembles_payload():
    client = BoostyClient("podbox", "auth.json")
    client._api = _fake_api({}, request_ret={"data": {"id": "post-9"}})

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

    call = client._api.request.await_args
    assert call.args[0] == "POST"
    assert call.args[1].endswith("/v1/blog/podbox/post/")

    payload = call.kwargs["data"]
    assert payload["title"] == "751. Послешоу"
    assert payload["subscription_level_id"] == "407063"
    assert payload["price"] == "10"

    data = json.loads(payload["data"])
    assert any(b.get("type") == "audio_file" and b["id"] == "aud-1" for b in data)

    teaser = json.loads(payload["teaser_data"])
    assert teaser[0]["type"] == "image"
    assert teaser[0]["id"] == "img-1"
