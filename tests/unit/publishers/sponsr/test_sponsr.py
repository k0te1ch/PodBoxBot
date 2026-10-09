"""Sponsr publisher: сессия, выжимка HAR и честный отказ до калибровки."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from app.publishers.Sponsr.sponsr_client import (
    SponsrAuthError,
    SponsrClient,
    SponsrNotCalibratedError,
    load_session,
    save_session,
)
from app.shared.publishers.har import summarize
from sagenza_tgbot_sdk.masking import default_masker, mask_secrets


def _client(tmp_path, handler, project="podbox"):
    session = tmp_path / "s.json"
    save_session(str(session), "sess-1", "UA")
    http = httpx.AsyncClient(
        base_url="https://sponsr.ru", transport=httpx.MockTransport(handler), cookies={"SESS": "sess-1"}
    )
    return SponsrClient(str(session), project, http=http)


@pytest.mark.asyncio
async def test_valid_session_passes(tmp_path):
    client = _client(tmp_path, lambda r: httpx.Response(200, text="ok"))

    await client.ensure_auth()


@pytest.mark.asyncio
async def test_redirect_to_login_is_auth_error(tmp_path):
    client = _client(tmp_path, lambda r: httpx.Response(302, headers={"location": "/auth/"}))

    with pytest.raises(SponsrAuthError, match="sponsr_session.json"):
        await client.ensure_auth()


@pytest.mark.asyncio
async def test_missing_project_is_auth_error(tmp_path):
    client = _client(tmp_path, lambda r: httpx.Response(200), project=None)

    with pytest.raises(SponsrAuthError, match="SPONSR_PROJECT"):
        await client.ensure_auth()


@pytest.mark.asyncio
async def test_publish_is_not_calibrated_yet(tmp_path):
    client = _client(tmp_path, lambda r: httpx.Response(200))

    with pytest.raises(SponsrNotCalibratedError, match="HAR"):
        await client.publish(title="t", content="c", path="p")


def test_har_summary_hides_values(tmp_path):
    har = {
        "log": {
            "entries": [
                {
                    "request": {
                        "method": "POST",
                        "url": "https://sponsr.ru/api/post/create?x=1",
                        "queryString": [{"name": "x", "value": "1"}],
                        "headers": [{"name": "X-CSRF-Token", "value": "secret-csrf"}],
                        "postData": {
                            "mimeType": "application/x-www-form-urlencoded",
                            "text": "title=Secret&level=5",
                        },
                    },
                    "response": {"status": 200, "content": {"mimeType": "application/json", "text": '{"id": 7}'}},
                },
                {
                    "request": {"method": "GET", "url": "https://sponsr.ru/static/app.js", "headers": []},
                    "response": {"status": 200, "content": {}},
                },
                {
                    "request": {"method": "GET", "url": "https://other.site/x", "headers": []},
                    "response": {"status": 200, "content": {}},
                },
            ]
        }
    }
    path = tmp_path / "s.har"
    path.write_text(json.dumps(har), encoding="utf-8")

    lines = summarize(path, "sponsr.ru")

    assert len(lines) == 1
    assert "POST sponsr.ru/api/post/create" in lines[0]
    assert "level, title" in lines[0]
    assert "X-CSRF-Token" in lines[0]
    assert "{id: int}" in lines[0]
    assert "Secret" not in lines[0]
    assert "secret-csrf" not in lines[0]


@pytest.mark.asyncio
async def test_handler_reports_calibration_error(event_dict, monkeypatch):
    from app.publishers.Sponsr import main

    client = AsyncMock()
    client.publish = AsyncMock(side_effect=SponsrNotCalibratedError())
    monkeypatch.setattr(main._publisher, "client", client)
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    client.publish.assert_awaited_once()
    result = producer.send.await_args.args[1]
    assert result["status"] == "failure"
    assert "HAR" in result["error"]


def test_session_cookie_from_the_file_is_masked(tmp_path):
    """Кука сессии вырезается из логов и текста ошибок."""
    path = str(tmp_path / "sponsr_session.json")
    save_session(path, "sponsr-session-value", "UA")
    try:
        load_session(path)

        text = mask_secrets("HTTP 403: SESS sponsr-session-value rejected")
    finally:
        default_masker.clear()

    assert text == "HTTP 403: SESS *** rejected"
