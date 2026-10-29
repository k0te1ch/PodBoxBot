"""Sponsr publisher: клиент веб-редактора на обезличенных ответах и хендлер на моках."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from app.publishers.Sponsr import sponsr_client
from app.publishers.Sponsr.sponsr_client import (
    SponsrApiError,
    SponsrAuthError,
    SponsrClient,
    load_session,
    parse_editor_page,
    safe_file_name,
    save_session,
)
from app.shared.publishers.har import summarize
from sagenza_tgbot_sdk.masking import default_masker, mask_secrets
from sagenza_tgbot_sdk.resilience import PermanentError

# Кусок страницы /<slug>/manage/post/new/ с обезличенными id.
EDITOR_PAGE = """
<button class="button danger js-toggle-project-offline" data-id="111" >Скрыть</button>
<select id="level_id" name="level_id" data-old-value="222" class="">
  <option value=""> Публичный пост </option>
  <option value="post_onetime" >Разовая покупка</option>
  <option value="222" selected > Базовый </option>
</select>
"""


class FakeSponsr:
    """Обезличенный sponsr.ru: пути, поля и ответы как в записи редактора."""

    def __init__(self):
        self.requests = []
        self.received = b""
        self.file_polls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if path == "/podbox/manage/post/new/":
            return httpx.Response(200, text=EDITOR_PAGE)
        if path == "/project/111/manage/resumable-file/" and method == "GET":
            return httpx.Response(
                200, json={"response": {"status": "UPLOAD", "last_byte": 0, "file_id": 333, "file_name": "ep.mp3"}}
            )
        if path == "/project/111/manage/resumable-file/":
            form = _multipart(request)
            self.received += form["file"]
            done = form["completed"] == b"1"
            return httpx.Response(
                200,
                json={
                    "response": {
                        "status": "DONE" if done else "PARTLY_DONE",
                        "file_upload_uid": form["file_upload_uid"].decode(),
                        "last_byte": form["last_byte"].decode(),
                        "completed": int(done),
                        "file_hash": "h",
                    }
                },
            )
        if path == "/project/111/manage/file-state/":
            self.file_polls += 1
            state = "completed" if self.file_polls > 1 else "uploading"
            return httpx.Response(
                200, json={"response": {"file_upload_state": state, "file_duration": "1271.4", "completed": 1}}
            )
        if path.startswith("/project/111/manage/upload-file-info/"):
            return httpx.Response(200, json={"response": {}})
        if path == "/project/111/manage/post-save/new":
            return httpx.Response(200, json={"response": {"url": "/podbox/manage/published", "post_id": 444}})
        if path == "/api/v2/content/posts/":
            return httpx.Response(200, json={"total": 1, "list": [{"id": 444, "level_id": 222}], "page": 1})
        return httpx.Response(404)


def _multipart(request: httpx.Request) -> dict[str, bytes]:
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields = {}
    for part in request.content.split(b"--" + boundary):
        if b"\r\n\r\n" not in part:
            continue
        head, value = part.split(b"\r\n\r\n", 1)
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        fields[name] = value[:-2]
    return fields


def _form(request: httpx.Request) -> dict:
    return dict(httpx.QueryParams(request.content.decode()))


def _client(tmp_path, handler, project="podbox", level_id=None):
    session = tmp_path / "s.json"
    save_session(str(session), "sess-1", "UA")
    http = httpx.AsyncClient(
        base_url="https://sponsr.ru", transport=httpx.MockTransport(handler), cookies={"SESS": "sess-1"}
    )
    return SponsrClient(str(session), project, level_id, http=http, poll_delay=0)


@pytest.mark.asyncio
async def test_full_publish_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(sponsr_client, "CHUNK_SIZE", 4)
    fake = FakeSponsr()
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"ID3-0123456")
    client = _client(tmp_path, fake)

    post_id = await client.publish(title="T", content="<p>текст</p>", teaser="текст", path=str(mp3))

    assert post_id == "444"
    assert fake.received == b"ID3-0123456"
    assert await client.get_post(post_id) == {"id": 444, "level_id": 222}
    assert client.post_url(post_id) == "https://sponsr.ru/podbox/444/"

    start = next(r for r in fake.requests if r.url.path.endswith("/resumable-file/") and r.method == "GET")
    assert start.url.params["file_upload_uid"] == "111_11_ep.mp3"
    assert start.url.params["file_category"] == "podcast"
    assert start.url.params["file_type"] == "audio/mpeg"
    chunks = [_multipart(r) for r in fake.requests if r.url.path.endswith("/resumable-file/") and r.method == "POST"]
    assert [c["last_byte"] for c in chunks] == [b"4", b"8", b"11"]
    assert [c["completed"] for c in chunks] == [b"0", b"0", b"1"]
    assert chunks[0]["file_id"] == b"333"
    updates = [_form(r) for r in fake.requests if r.url.path.endswith("/update-chunk-file")]
    assert [u["last_byte"] for u in updates] == ["4", "8", "11"]
    complete = next(r for r in fake.requests if r.url.path.endswith("/complete-file"))
    assert _form(complete) == {"file_id": "333", "file_category": "podcast"}
    assert complete.headers["e"] == "true"
    assert complete.headers["x-requested-with"] == "XMLHttpRequest"

    save = _form(next(r for r in fake.requests if r.url.path.endswith("/post-save/new")))
    assert save["level_id"] == "222"
    assert save["project_id"] == "111"
    assert save["media_file"] == "333"
    assert save["post_status"] == "active"
    assert save["post_access_type"] == "def"
    assert save["post_duration_podcast"] == "1271"
    assert save["post_title"] == "T"
    assert save["post_text"] == "<p>текст</p>"
    assert save["post_teaser"] == "текст"
    assert len(save["post_date"]) == 19


@pytest.mark.asyncio
async def test_configured_level_wins(tmp_path):
    fake = FakeSponsr()
    client = _client(tmp_path, fake, level_id="999")

    await client.save_post(title="T", content="<p>c</p>", teaser="c", file_id="333", duration=1)

    save = _form(next(r for r in fake.requests if r.url.path.endswith("/post-save/new")))
    assert save["level_id"] == "999"


def test_parse_editor_page():
    assert parse_editor_page(EDITOR_PAGE) == ("111", "222")
    assert parse_editor_page("<html></html>") == (None, None)


def test_safe_file_name_matches_editor():
    assert safe_file_name("0771_postshow (final)!.mp3") == "0771_postshow final.mp3"


@pytest.mark.asyncio
async def test_page_without_project_is_auth_error(tmp_path):
    client = _client(tmp_path, lambda r: httpx.Response(200, text="<html>вход</html>"))

    with pytest.raises(SponsrAuthError, match="id проекта"):
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
async def test_error_body_is_raised(tmp_path):
    fake = FakeSponsr()

    def handler(request):
        if request.url.path.endswith("/post-save/new"):
            return httpx.Response(200, json={"error": {"code": 1}})
        return fake(request)

    client = _client(tmp_path, handler)

    with pytest.raises(SponsrApiError, match="save post"):
        await client.save_post(title="T", content="c", teaser="c", file_id="1", duration=1)


@pytest.mark.asyncio
async def test_failed_file_is_permanent(tmp_path):
    fake = FakeSponsr()

    def handler(request):
        if request.url.path.endswith("/file-state/"):
            return httpx.Response(200, json={"response": {"file_upload_state": "failed"}})
        return fake(request)

    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"ID3")
    client = _client(tmp_path, handler)

    with pytest.raises(PermanentError, match="failed"):
        await client.upload_audio(str(mp3))


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


@pytest.fixture
def publisher(monkeypatch):
    from app.publishers.Sponsr import main

    client = AsyncMock()
    client.publish = AsyncMock(return_value="444")
    client.get_post = AsyncMock(return_value={"id": 444})
    client.post_url = lambda pid: f"https://sponsr.ru/podbox/{pid}/"
    monkeypatch.setattr(main._publisher, "client", client)
    return main, client


@pytest.mark.asyncio
async def test_handler_publishes(event_dict, publisher):
    main, client = publisher
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    kwargs = client.publish.await_args.kwargs
    assert kwargs["path"] == "/app/files/0042_postshow.mp3"
    assert kwargs["teaser"] == "Описание"
    assert "<p>Описание</p>" in kwargs["content"]
    result = producer.send.await_args.args[1]
    assert result["status"] == "success"
    assert result["metadata"]["url"] == "https://sponsr.ru/podbox/444/"


@pytest.mark.asyncio
async def test_handler_reports_auth_error(event_dict, publisher):
    main, client = publisher
    client.ensure_auth = AsyncMock(side_effect=SponsrAuthError("сессия не принята"))
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    client.publish.assert_not_awaited()
    result = producer.send.await_args.args[1]
    assert result["status"] == "failure"
    assert "import-cookie" in result["error"]


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
