"""Бизнес-метрики бота: что попадает в реестр /metrics и с какими метками."""

from unittest.mock import patch

import pytest
from prometheus_client.parser import text_string_to_metric_families

from services.kafka.handlers.upload_event import record_publish_metrics
from services.metrics import BotMetrics, episode_kind, episode_number, expected_platforms


class FakeRedis:
    """Хеши Redis в памяти: ровно те команды, что нужны журналу эпизодов."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}

    async def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update({k: str(v) for k, v in mapping.items()})

    async def hincrby(self, key, field, amount):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = str(int(bucket.get(field, 0)) + amount)
        return int(bucket[field])

    async def hsetnx(self, key, field, value):
        bucket = self.hashes.setdefault(key, {})
        if field in bucket:
            return 0
        bucket[field] = str(value)
        return 1

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hmget(self, key, fields):
        return [self.hashes.get(key, {}).get(f) for f in fields]

    async def expire(self, key, seconds):
        return True


def samples(metrics: BotMetrics) -> dict[tuple[str, tuple], float]:
    result = {}
    for family in text_string_to_metric_families(metrics.sdk.render().decode()):
        for sample in family.samples:
            result[(sample.name, tuple(sorted(sample.labels.items())))] = sample.value
    return result


def value(metrics: BotMetrics, name: str, **labels: str) -> float | None:
    return samples(metrics).get((name, tuple(sorted({"bot": "podboxbot", **labels}.items()))))


@pytest.fixture
def metrics():
    metrics = BotMetrics()
    metrics.use_redis(FakeRedis())
    return metrics


def test_process_metrics_are_exposed(metrics):
    names = {name for name, _labels in samples(metrics)}
    assert "process_resident_memory_bytes" in names or "python_info" in names
    assert "python_gc_collections_total" in names


@pytest.mark.parametrize(
    ("number", "file_name", "expected"),
    [("767", None, "767"), (None, "0767_rz_26092026.mp3", "767"), (None, "/app/files/0012_postshow_1.mp3", "12")],
)
def test_episode_number(number, file_name, expected):
    assert episode_number(number, file_name) == expected


def test_episode_number_rejects_garbage():
    assert episode_number(None, "notes.txt") is None
    assert episode_number("abc") is None


def test_episode_kind_merges_postshow_alias():
    assert episode_kind("postshow") == "aftershow"
    assert episode_kind(None) == "unknown"


@pytest.mark.asyncio
async def test_second_press_for_the_same_episode_is_a_repeat(metrics):
    await metrics.publish_requested("wp", "main", number="767")
    await metrics.publish_requested("wp", "main", number="767")
    await metrics.publish_requested("ftp", "main", file_name="0767_rz_26092026.mp3")

    name = "sagenza_event_publish_requested_total"
    assert value(metrics, name, platform="wp", type_episode="main", attempt="first") == 1
    assert value(metrics, name, platform="wp", type_episode="main", attempt="repeat") == 1
    assert value(metrics, name, platform="ftp", type_episode="main", attempt="first") == 1


@pytest.mark.asyncio
async def test_time_to_publish_per_platform_and_everywhere(metrics):
    with patch("services.metrics.time.time", return_value=1000.0):
        await metrics.episode_prepared("767", "main", "upload", received_at=1000.0, size_bytes=50 * 2**20)
    for platform, at in (("ftp", 1060.0), ("wp", 1300.0), ("telegram", 1600.0)):
        with patch("services.metrics.time.time", return_value=at):
            await metrics.publish_succeeded(platform, "main", "published", number="767")

    count = "podboxbot_time_to_publish_seconds_count"
    total = "podboxbot_time_to_publish_seconds_sum"
    assert value(metrics, count, platform="wp", type_episode="main") == 1
    assert value(metrics, total, platform="wp", type_episode="main") == 300
    assert value(metrics, "podboxbot_time_to_publish_all_seconds_sum", type_episode="main") == 600
    assert value(metrics, "podboxbot_episode_audio_size_bytes_count", type_episode="main") == 1
    published = "sagenza_event_episode_published_total"
    assert value(metrics, published, platform="telegram", type_episode="main", action="published") == 1


@pytest.mark.asyncio
async def test_repeated_publication_does_not_count_time_twice(metrics):
    await metrics.episode_prepared("5", "aftershow", "rss", received_at=0.0)
    await metrics.publish_succeeded("boosty", "aftershow", "draft", number="5")
    await metrics.publish_succeeded("boosty", "aftershow", "published", number="5")

    assert value(metrics, "podboxbot_time_to_publish_seconds_count", platform="boosty", type_episode="aftershow") == 1
    assert value(metrics, "podboxbot_time_to_publish_all_seconds_count", type_episode="aftershow") is None


def test_aftershow_goes_to_enabled_paid_platforms_only():
    with patch("config.BOOSTY_ENABLED", True), patch("config.VK_ENABLED", False):
        assert expected_platforms("aftershow") == {"ftp", "boosty"}
    assert expected_platforms("main") == {"ftp", "wp", "telegram"}


@pytest.mark.asyncio
async def test_metrics_without_redis_still_count_events():
    metrics = BotMetrics()
    await metrics.publish_requested("ftp", "main", number="1")
    await metrics.publish_succeeded("ftp", "main", None, number="1")

    assert value(
        metrics, "sagenza_event_publish_requested_total", platform="ftp", type_episode="main", attempt="first"
    )
    assert value(metrics, "podboxbot_time_to_publish_seconds_count", platform="ftp", type_episode="main") is None


@pytest.mark.asyncio
async def test_broken_redis_does_not_break_the_bot(metrics):
    class Broken(FakeRedis):
        async def hincrby(self, *args):
            raise ConnectionError("redis is down")

    metrics.use_redis(Broken())
    await metrics.publish_requested("wp", "main", number="1")  # не должно упасть


def test_active_admins_count_distinct_users_without_ids(metrics):
    metrics.admin_seen(1)
    metrics.admin_seen(1)
    metrics.admin_seen(2)

    assert value(metrics, "podboxbot_active_admins", window="1d") == 2
    labels = {labels for _name, labels in samples(metrics) if _name == "podboxbot_active_admins"}
    assert all(dict(item).keys() == {"bot", "window"} for item in labels)


def test_upload_dialog_steps(metrics):
    metrics.upload_step("mp3", "done")
    metrics.upload_step("template", "invalid")

    assert value(metrics, "sagenza_event_upload_step_total", step="template", outcome="invalid") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "name", "labels"),
    [
        (
            "failure",
            "sagenza_event_publish_failed_total",
            {"platform": "wp", "type_episode": "main", "stage": "verify"},
        ),
        ("retrying", "sagenza_event_publish_retry_total", {"platform": "wp", "stage": "verify"}),
    ],
)
async def test_result_events_are_counted_by_topic_platform(metrics, status, name, labels):
    event = {"event_type": "result", "status": status, "number": "7", "type_episode": "main"}
    event["metadata"] = {"stage": "verify"}
    with patch("services.kafka.handlers.upload_event.bot_metrics", metrics):
        await record_publish_metrics(event, "wp")

    assert value(metrics, name, **labels) == 1


@pytest.mark.asyncio
async def test_progress_events_are_not_counted(metrics):
    with patch("services.kafka.handlers.upload_event.bot_metrics", metrics):
        await record_publish_metrics({"event_type": "progress", "status": "pending"}, "ftp")

    assert not any(name.startswith("sagenza_event_publish") for name, _labels in samples(metrics))
