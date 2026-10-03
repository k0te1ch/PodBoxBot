"""Режимы Boosty: черновик и отложенная публикация на уровне клиента и publisher'а.

Ответы API лежат в ``fixtures/``. Форма ответа ``post_draft/publish/`` для
немедленной публикации взята из HAR веб-редактора (2026-05-31, id и числа
заменены). Ответы для отложенного поста собраны по полям, которые читает
веб-редактор Boosty (``isPublished``, ``publishTime``, сверено с его JS
2026-09-30): живьём отложенный пост ещё не создавался, после смоука их нужно
заменить записанными.
"""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from app.publishers.Boosty.boosty_client import BoostyClient, BoostyPublishedNowError, PostContent, Response
from boosty_auth import AuthData, save

FIXTURES = Path(__file__).parent / "fixtures"
POST_ID = "5e21a9d4-7b3f-4f0e-8c12-9d6e4a0b3f71"


def recorded(name: str, status: int = 200) -> Response:
    return Response(status, (FIXTURES / name).read_bytes())


class FakeTransport:
    """Отвечает по первому подходящему правилу (метод, суффикс URL), пишет запросы."""

    def __init__(self, rules):
        self.rules = rules
        self.calls = []

    async def send(self, method, url, *, headers, data=None, json_body=None, params=None):
        self.calls.append({"method": method, "url": url, "data": data})
        for rule_method, suffix, response in self.rules:
            if method == rule_method and url.endswith(suffix):
                return response
        raise AssertionError(f"unexpected request {method} {url}")


@pytest.fixture
def auth_file(tmp_path):
    path = tmp_path / "boosty_auth.json"
    save(path, AuthData(access_token="a", refresh_token="r", expires_at=int(time.time()) + 86400, device_id="d"))
    return path


@pytest.fixture
def post():
    return PostContent(
        title="751. Послешоу",
        body="описание",
        chapters=[["00:00", "Начало"]],
        audio_id="aud-1",
        audio_size=555,
        audio_title="ep.mp3",
        cover_id="img-1",
        subscription_level_id="407063",
        price=10,
    )


def client_with(auth_file, rules):
    transport = FakeTransport(rules)
    return BoostyClient("podbox", str(auth_file), transport=transport), transport


# --- клиент -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_now_sends_draft_then_publish(auth_file, post):
    client, transport = client_with(
        auth_file,
        [("PUT", "/post_draft", recorded("post_draft.json")), ("POST", "/publish/", recorded("publish_now.json"))],
    )

    assert await client.publish(post) == "0b7f3c2e-5d1a-4c8e-9f60-2a4d8b1e7c35"

    put, pub = transport.calls
    assert "publish_time" not in put["data"]
    assert pub["data"] == {"is_showcase_visible": "true"}


@pytest.mark.asyncio
async def test_save_draft_never_calls_publish(auth_file, post):
    client, transport = client_with(auth_file, [("PUT", "/post_draft", recorded("post_draft.json"))])

    await client.save_draft(post)

    assert [(c["method"], c["url"].rsplit("/v1", 1)[1]) for c in transport.calls] == [
        ("PUT", "/blog/podbox/post_draft")
    ]


@pytest.mark.asyncio
async def test_get_draft_reads_the_blog_draft(auth_file):
    client, _ = client_with(auth_file, [("GET", "/post_draft", recorded("post_draft.json"))])

    assert (await client.get_draft())["title"] == "751. Послешоу"


@pytest.mark.asyncio
async def test_get_draft_on_empty_blog_is_none(auth_file):
    client, _ = client_with(auth_file, [("GET", "/post_draft", recorded("post_draft_empty.json"))])

    assert await client.get_draft() is None


@pytest.mark.asyncio
async def test_schedule_sends_publish_time_on_both_requests(auth_file, post):
    client, transport = client_with(
        auth_file,
        [
            ("PUT", "/post_draft", recorded("post_draft.json")),
            ("POST", "/publish/", recorded("publish_scheduled.json")),
        ],
    )
    publish_time = int(time.time()) + 366 * 24 * 3600

    scheduled = await client.schedule(post, publish_time, showcase=False)

    assert scheduled["id"] == POST_ID
    assert scheduled["isPublished"] is False
    put, pub = transport.calls
    assert put["data"]["publish_time"] == str(publish_time)
    assert pub["data"] == {"publish_time": str(publish_time), "is_showcase_visible": "false"}


@pytest.mark.asyncio
async def test_schedule_reports_a_post_published_right_away(auth_file, post):
    client, _ = client_with(
        auth_file,
        [
            ("PUT", "/post_draft", recorded("post_draft.json")),
            ("POST", "/publish/", recorded("publish_ignored_time.json")),
        ],
    )

    with pytest.raises(BoostyPublishedNowError) as exc:
        await client.schedule(post, int(time.time()) + 3600)
    assert exc.value.post_id == "9a0c4e7b-2f18-4d65-b3a9-1c7e5d2f8b40"


@pytest.mark.asyncio
async def test_schedule_refuses_a_time_in_the_past(auth_file, post):
    # Прошедшее время Boosty может принять как «опубликовать сейчас».
    client, transport = client_with(auth_file, [])

    with pytest.raises(ValueError, match="future"):
        await client.schedule(post, int(time.time()) - 60)
    assert transport.calls == []


@pytest.mark.asyncio
async def test_delete_post(auth_file):
    client, transport = client_with(auth_file, [("DELETE", f"/post/{POST_ID}", Response(200, b"{}"))])

    await client.delete_post(POST_ID)

    assert transport.calls[0]["method"] == "DELETE"
    assert transport.calls[0]["url"].endswith(f"/v1/blog/podbox/post/{POST_ID}")


# --- publisher --------------------------------------------------------------


@pytest.fixture
def publisher(monkeypatch):
    from app.publishers.Boosty import main

    client = AsyncMock()
    client.upload_audio = AsyncMock(return_value=("aud-1", 123))
    client.upload_image = AsyncMock(return_value="img-1")
    client.publish = AsyncMock(return_value="post-1")
    client.save_draft = AsyncMock(return_value=None)
    client.get_draft = AsyncMock(return_value=json.loads(recorded("post_draft.json").body)["data"]["postDraft"])
    client.schedule = AsyncMock(return_value=json.loads(recorded("publish_scheduled.json").body)["data"]["post"])
    client.get_post = AsyncMock(return_value=json.loads(recorded("get_scheduled_post.json").body)["data"])
    monkeypatch.setattr(main._publisher, "client", client)
    monkeypatch.setattr(main, "BOOSTY_BLOG", "razgovorny")
    monkeypatch.setattr(main, "BOOSTY_OWNER_ID", 1900545)
    monkeypatch.setattr(main, "BOOSTY_SUBSCRIPTION_LEVEL_ID", "407063")
    return main, client


@pytest.fixture
def event_dict(sample_boosty_event_dict):
    return {**sample_boosty_event_dict, "title": "751. Послешоу"}


def _result(producer) -> dict:
    return [c.args[1] for c in producer.send.call_args_list if c.args[1]["event_type"] == "result"][-1]


@pytest.mark.asyncio
async def test_default_mode_publishes_right_away(publisher, event_dict):
    main, client = publisher
    client.get_post.return_value = {"id": "post-1", "isPublished": True}
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    client.publish.assert_awaited_once()
    client.save_draft.assert_not_awaited()
    client.schedule.assert_not_awaited()
    assert _result(producer)["metadata"]["action"] == "published"


@pytest.mark.asyncio
async def test_chosen_publication_time_schedules_the_post(publisher, event_dict, monkeypatch):
    """Время, выбранное при оформлении выпуска, важнее режима publish."""
    main, client = publisher
    monkeypatch.setattr(main.config, "TIMEZONE", "UTC")
    monkeypatch.setattr(main.time, "time", lambda: 1_790_000_000.0)  # 2026-09-22
    producer = AsyncMock()

    await main.handle_upload({**event_dict, "publish_at": "2026-10-05T20:00"}, producer)

    client.publish.assert_not_awaited()
    # 20:00 5 октября 2026 года во времени сервиса (в тесте это UTC).
    assert client.schedule.await_args.args[1] == 1_791_230_400
    result = _result(producer)
    assert result["metadata"]["action"] == "scheduled"
    assert result["metadata"]["publish_at"].startswith("05.10.2026 20:00")


@pytest.mark.asyncio
@pytest.mark.parametrize("publish_at", ["2026-09-01T10:00", "soon", None])
async def test_passed_or_unreadable_time_publishes_by_the_mode(publisher, event_dict, monkeypatch, publish_at):
    main, client = publisher
    monkeypatch.setattr(main.config, "TIMEZONE", "UTC")
    monkeypatch.setattr(main.time, "time", lambda: 1_790_000_000.0)
    client.get_post.return_value = {"id": "post-1", "isPublished": True}
    producer = AsyncMock()

    await main.handle_upload({**event_dict, "publish_at": publish_at}, producer)

    client.publish.assert_awaited_once()
    client.schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_draft_mode_ignores_the_chosen_time(publisher, event_dict, monkeypatch):
    main, client = publisher
    monkeypatch.setattr(main, "BOOSTY_PUBLISH_MODE", "draft")
    monkeypatch.setattr(main.time, "time", lambda: 1_790_000_000.0)
    producer = AsyncMock()

    await main.handle_upload({**event_dict, "publish_at": "2026-10-05T20:00"}, producer)

    client.save_draft.assert_awaited_once()
    client.schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_draft_mode_saves_draft_without_publishing(publisher, event_dict, monkeypatch):
    main, client = publisher
    monkeypatch.setattr(main, "BOOSTY_PUBLISH_MODE", "draft")
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    client.save_draft.assert_awaited_once()
    assert client.save_draft.await_args.args[0].title == "751. Послешоу"
    client.publish.assert_not_awaited()
    client.schedule.assert_not_awaited()
    result = _result(producer)
    assert result["status"] == "success"
    assert result["post_id"] is None
    assert result["metadata"] == {
        "platform": "boosty",
        "action": "draft",
        "url": "https://boosty.to/razgovorny/new-post",
    }


@pytest.mark.asyncio
async def test_draft_mode_fails_when_the_draft_is_not_saved(publisher, event_dict, monkeypatch):
    main, client = publisher
    monkeypatch.setattr(main, "BOOSTY_PUBLISH_MODE", "draft")
    client.get_draft.return_value = {"title": "что-то другое"}
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    result = _result(producer)
    assert result["status"] == "failure"
    assert result["metadata"]["stage"] == "verify"


@pytest.mark.asyncio
async def test_scheduled_mode_creates_a_deferred_post(publisher, event_dict, monkeypatch):
    main, client = publisher
    monkeypatch.setattr(main, "BOOSTY_PUBLISH_MODE", "scheduled")
    monkeypatch.setattr(main, "BOOSTY_SCHEDULE_DELAY_HOURS", 48)
    producer = AsyncMock()
    before = time.time()

    await main.handle_upload(event_dict, producer)

    client.publish.assert_not_awaited()
    publish_time = client.schedule.await_args.args[1]
    assert before + 48 * 3600 - 1 <= publish_time <= time.time() + 48 * 3600
    client.get_post.assert_awaited_once_with(POST_ID)
    result = _result(producer)
    assert result["status"] == "success"
    assert result["post_id"] == POST_ID
    assert result["metadata"]["action"] == "scheduled"
    assert result["metadata"]["publish_at"]
    assert result["metadata"]["url"] == f"https://boosty.to/razgovorny/posts/{POST_ID}"


@pytest.mark.asyncio
async def test_scheduled_post_that_went_public_is_not_retried(publisher, event_dict, monkeypatch):
    main, client = publisher
    monkeypatch.setattr(main, "BOOSTY_PUBLISH_MODE", "scheduled")
    client.schedule.side_effect = BoostyPublishedNowError("post-x")
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    # Повтор выложил бы второй пост.
    client.schedule.assert_awaited_once()
    result = _result(producer)
    assert result["status"] == "failure"
    assert "сразу" in result["error"]


@pytest.mark.asyncio
async def test_scheduled_post_seen_as_published_on_verify_is_a_failure(publisher, event_dict, monkeypatch):
    main, client = publisher
    monkeypatch.setattr(main, "BOOSTY_PUBLISH_MODE", "scheduled")
    client.get_post.return_value = {"id": POST_ID, "isPublished": True}
    producer = AsyncMock()

    await main.handle_upload(event_dict, producer)

    client.get_post.assert_awaited_once()
    assert _result(producer)["status"] == "failure"


# --- смоук ------------------------------------------------------------------


@pytest.fixture
def smoke(monkeypatch):
    from app.publishers.Boosty import smoke

    client = AsyncMock()
    client.upload_audio = AsyncMock(return_value=("aud-1", 123))
    client.upload_image = AsyncMock(return_value="img-1")
    client.schedule = AsyncMock(return_value={"id": POST_ID, "isPublished": False})
    client.get_post = AsyncMock(
        side_effect=[{"id": POST_ID, "isPublished": False}, {"id": POST_ID, "isDeleted": True}]
    )
    monkeypatch.setattr(smoke, "_client", lambda: client)
    monkeypatch.setattr(smoke.config, "BOOSTY_SUBSCRIPTION_LEVEL_ID", "407063")
    monkeypatch.setattr(smoke.config, "BOOSTY_OWNER_ID", 1900545)
    return smoke, client


def test_smoke_schedule_creates_a_year_ahead_and_deletes_only_its_post(smoke):
    module, client = smoke

    assert module.main(["schedule", "--mp3", "/app/files/test.mp3"]) == 0

    post, publish_time = client.schedule.await_args.args
    assert post.title.startswith("[e2e-test ")
    assert publish_time >= time.time() + 365 * 24 * 3600
    assert client.schedule.await_args.kwargs == {"showcase": False}
    client.delete_post.assert_awaited_once_with(POST_ID)


def test_smoke_schedule_deletes_a_post_published_right_away(smoke):
    module, client = smoke
    # Сервис и смоук импортируют клиент без пакета: исключение берётся оттуда же.
    client.schedule.side_effect = module.BoostyPublishedNowError("post-x")

    assert module.main(["schedule", "--mp3", "/app/files/test.mp3"]) == 3

    client.delete_post.assert_awaited_once_with("post-x")
