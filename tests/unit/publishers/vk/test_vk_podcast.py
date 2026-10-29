"""VK, режим podcast: запросы раздела подкастов vk.ru на обезличенных ответах."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from sagenza_tgbot_sdk.masking import default_masker, mask_secrets
from sagenza_tgbot_sdk.resilience import PermanentError
from vk_client import VkAuthError
from vk_podcast import (
    PRIVACY_ALL,
    VkPodcastClient,
    VkSessionError,
    VkWebError,
    load_session,
    parse_cookie_header,
    save_session,
)

GROUP = 100
UPLOAD_URL = "https://pu.test/gu/audio/v2/upload?token=upload-token"
# Ответы vk.ru в форме записи, все id и хэши заменены.
ADD_BOX = {
    "payload": [
        0,
        [
            '<div class="podcast_add_privacy">Кому доступен эпизод</div>',
            '<div class="ui_gallery_item" data-item-id="-100_201"></div>'
            '<div class="ui_gallery_item" data-item-id="-100_202"></div>',
            "cur.lang = {};",
            {"audio": "", "hash": "", "audio_upload": {"url": UPLOAD_URL, "vars": {"act": "load_audio"}}},
        ],
    ]
}
UPLOADER = {"sha": "s", "secret": "x", "meta": {}, "hash": "h", "server": "1", "user_id": 1, "group_id": GROUP}
EPISODE = [301, -GROUP, "", "Title", "Podcast", 60, -102, 0, "", 0, 0, "", '{"podcast":true,"private":true}']
DONE_ADD = {"payload": [0, [[EPISODE, "edit-hash"]]]}
PAID = EPISODE[:12] + ['{"podcast":true,"private":true,"paid":true}']
A_EDIT = {"payload": [0, [PAID]]}


class FakeVk:
    def __init__(self, a_edit=None):
        self.requests = []
        self.a_edit = a_edit or A_EDIT

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.path
        form = _form(request) if request.headers.get("content-type", "").startswith("application/x-www") else {}
        if host == "vk.ru" and path == "/al_podcasts.php" and form.get("act") == "a_add_box":
            return httpx.Response(200, json=ADD_BOX)
        if host == "pu.test":
            return httpx.Response(200, json=UPLOADER)
        if host == "vk.ru" and path == "/al_audio.php":
            return httpx.Response(200, json=DONE_ADD)
        if host == "vk.ru" and path == "/al_podcasts.php" and form.get("act") == "a_edit":
            return httpx.Response(200, json=self.a_edit)
        if host == "login.vk.ru":
            return httpx.Response(200, json={"type": "okay", "data": {"access_token": "web-token-1", "expires": 1}})
        if path == "/method/wall.post":
            return httpx.Response(200, json={"response": {"post_id": 77}})
        if path == "/method/wall.getById":
            return httpx.Response(200, json={"response": {"items": [{"id": 77}]}})
        return httpx.Response(404)


def _form(request: httpx.Request) -> dict:
    return dict(httpx.QueryParams(request.content.decode()))


def _find(fake: FakeVk, **match) -> httpx.Request:
    for request in fake.requests:
        form = _form(request) if b"=" in request.content and b"Content-Disposition" not in request.content else {}
        if all(form.get(k) == v for k, v in match.items()):
            return request
    raise AssertionError(f"no request with {match}")


@pytest.fixture
def session_file(tmp_path):
    path = tmp_path / "vk_session.json"
    save_session(str(path), "remixsid=cookie-value-1; remixlang=0", "UA")
    yield str(path)
    default_masker.clear()


def _patch(monkeypatch, handler):
    real = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)


@pytest.mark.asyncio
async def test_full_podcast_flow(tmp_path, session_file, monkeypatch):
    fake = FakeVk()
    _patch(monkeypatch, fake)
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"ID3")
    client = VkPodcastClient(session_file, GROUP)

    post_id = await client.publish(str(mp3), title="42. Послешоу", desc="Описание", message="42. Послешоу\n\nОписание")

    assert post_id == "77"
    assert await client.get_post(post_id) == {"id": 77}
    assert client.post_url(post_id) == "https://vk.ru/wall-100_77"

    add_box = _find(fake, act="a_add_box")
    form = _form(add_box)
    assert form["oid"] == "-100"
    assert form["ref"] == "podcasts"
    assert form["al"] == "1"
    assert len(form["boxhash"]) == 8
    assert add_box.headers["x-requested-with"] == "XMLHttpRequest"
    assert add_box.headers["referer"] == "https://vk.ru/podcasts-100"
    assert "remixsid=cookie-value-1" in add_box.headers["cookie"]

    upload = next(r for r in fake.requests if r.url.host == "pu.test")
    assert upload.url.params["token"] == "upload-token"
    assert b'name="file"' in upload.content

    done = _form(_find(fake, act="done_add"))
    assert json.loads(done["go_uploader_response"]) == UPLOADER
    assert done["podcast"] == "1"
    assert done["upldr"] == "1"

    edit = _form(_find(fake, act="a_edit"))
    assert edit["episode_full_id"] == "-100_301"
    assert edit["hash"] == "edit-hash"
    assert edit["privacy"] == "2"
    assert edit["cover_id"] == "-100_201"
    assert edit["title"] == "42. Послешоу"
    assert edit["desc"] == "Описание"

    login = next(r for r in fake.requests if r.url.host == "login.vk.ru")
    assert login.url.params["act"] == "web_token"
    assert _form(login)["app_id"] == "6287487"

    post = next(r for r in fake.requests if r.url.path == "/method/wall.post")
    assert post.url.host == "api.vk.ru"
    assert post.url.params["client_id"] == "6287487"
    post_form = _form(post)
    assert post_form["attachments"] == "podcast-100_301"
    assert post_form["owner_id"] == "-100"
    assert post_form["from_group"] == "1"
    assert post_form["access_token"] == "web-token-1"
    assert "donut_paid_duration" not in post_form


@pytest.mark.asyncio
async def test_configured_cover_and_public_episode(tmp_path, session_file, monkeypatch):
    fake = FakeVk(a_edit={"payload": [0, [EPISODE]]})
    _patch(monkeypatch, fake)
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"ID3")
    client = VkPodcastClient(session_file, GROUP, privacy=PRIVACY_ALL, cover_id="-100_999")

    assert await client.prepare_episode(str(mp3), title="T", desc="D") == "podcast-100_301"

    edit = _form(_find(fake, act="a_edit"))
    assert edit["cover_id"] == "-100_999"
    assert edit["privacy"] == "0"


@pytest.mark.asyncio
async def test_episode_without_lock_is_permanent_error(tmp_path, session_file, monkeypatch):
    _patch(monkeypatch, FakeVk(a_edit={"payload": [0, [EPISODE]]}))
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"ID3")

    with pytest.raises(PermanentError, match="без замка"):
        await VkPodcastClient(session_file, GROUP).prepare_episode(str(mp3), title="T", desc="D")


@pytest.mark.asyncio
async def test_html_instead_of_json_is_session_error(session_file, monkeypatch):
    _patch(monkeypatch, lambda r: httpx.Response(200, text="<html>login</html>"))

    with pytest.raises(VkSessionError, match="import-cookie"):
        await VkPodcastClient(session_file, GROUP).open_add_box()


@pytest.mark.asyncio
async def test_non_zero_payload_is_web_error(session_file, monkeypatch):
    _patch(monkeypatch, lambda r: httpx.Response(200, json={"payload": ["8", ["Access denied"]]}))

    with pytest.raises(VkWebError, match="код 8"):
        await VkPodcastClient(session_file, GROUP).open_add_box()


@pytest.mark.asyncio
async def test_missing_web_token_is_session_error(session_file, monkeypatch):
    _patch(monkeypatch, lambda r: httpx.Response(200, json={"type": "error", "error_info": "x"}))

    with pytest.raises(VkSessionError, match="токен"):
        await VkPodcastClient(session_file, GROUP).web_token()


@pytest.mark.asyncio
async def test_api_auth_error_is_classified(session_file, monkeypatch):
    def handler(request):
        if request.url.host == "login.vk.ru":
            return httpx.Response(200, json={"type": "okay", "data": {"access_token": "web-token-1"}})
        return httpx.Response(200, json={"error": {"error_code": 5, "error_msg": "auth"}})

    _patch(monkeypatch, handler)

    with pytest.raises(VkAuthError):
        await VkPodcastClient(session_file, GROUP).post("m", "podcast-100_301")


def test_cookie_header_parsing():
    assert parse_cookie_header("a=1; b=x=y;; c") == {"a": "1", "b": "x=y"}


def test_missing_session_file(tmp_path):
    with pytest.raises(VkSessionError, match="нет файла"):
        load_session(str(tmp_path / "nope.json"))


def test_session_cookies_are_masked(session_file):
    load_session(session_file)

    assert mask_secrets("cookie cookie-value-1 rejected") == "cookie *** rejected"


@pytest.fixture
def podcast_publisher(monkeypatch):
    from app.publishers.VK import main

    podcast = AsyncMock()
    podcast.prepare_episode = AsyncMock(return_value="podcast-100_301")
    podcast.post = AsyncMock(return_value="77")
    podcast.get_post = AsyncMock(return_value={"id": 77})
    podcast.post_url = lambda pid: f"https://vk.ru/wall-100_{pid}"
    monkeypatch.setattr(main._publisher, "podcast", podcast)
    monkeypatch.setattr(main._publisher, "media", "podcast")
    return main, podcast


@pytest.mark.asyncio
async def test_handler_publishes_podcast(event_dict, podcast_publisher):
    main, podcast = podcast_publisher
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    podcast.prepare_episode.assert_awaited_once()
    assert podcast.prepare_episode.await_args.kwargs["title"] == "42. Послешоу"
    message, attachment = podcast.post.await_args.args
    assert message.startswith("42. Послешоу")
    assert attachment == "podcast-100_301"
    result = producer.send.await_args.args[1]
    assert result["status"] == "success"
    assert result["metadata"]["url"] == "https://vk.ru/wall-100_77"


@pytest.mark.asyncio
async def test_handler_session_error_is_reported(event_dict, podcast_publisher):
    main, podcast = podcast_publisher
    podcast.web_token = AsyncMock(side_effect=VkSessionError("сессия не принята"))
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    podcast.prepare_episode.assert_not_awaited()
    result = producer.send.await_args.args[1]
    assert result["status"] == "failure"
    assert "import-cookie" in result["error"]
