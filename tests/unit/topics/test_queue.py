"""Очередь тем: модель, хранилище в Redis, лимит на сутки и проверки сервиса."""

import pytest
import pytz

from services.topics import (
    Author,
    DailyQuota,
    RedisTopicRepository,
    Refusal,
    Topic,
    TopicService,
    TopicSource,
    TopicStatus,
)


def _topic(text="обсудить подкасты про кино", user_id=7, message_id=None, created_at=1.0) -> Topic:
    return Topic(
        text=text,
        author=Author(name="@listener", user_id=user_id),
        source=TopicSource.HASHTAG,
        chat_id=-100 if message_id else None,
        message_id=message_id,
        created_at=created_at,
    )


def _service(redis, limit=2) -> TopicService:
    return TopicService(RedisTopicRepository(redis), DailyQuota(redis, limit, pytz.UTC), min_length=5, max_length=50)


def test_topic_survives_json_roundtrip():
    topic = _topic(message_id=5)
    topic.id = 3

    restored = Topic.from_json(topic.to_json())

    assert restored == topic
    assert isinstance(restored.status, TopicStatus)
    assert isinstance(restored.author, Author)


@pytest.mark.asyncio
async def test_repository_lists_by_status_newest_first(fake_redis):
    repo = RedisTopicRepository(fake_redis)
    first = await repo.add(_topic("первая тема", created_at=1))
    second = await repo.add(_topic("вторая тема", created_at=2))

    assert [t.text for t in await repo.list(TopicStatus.NEW)] == ["вторая тема", "первая тема"]

    moved = await repo.set_status(first.id, TopicStatus.TAKEN)

    assert moved.status is TopicStatus.TAKEN and moved.updated_at is not None
    assert (await repo.get(first.id)).status is TopicStatus.TAKEN
    assert [t.id for t in await repo.list(TopicStatus.NEW)] == [second.id]
    assert await repo.count(TopicStatus.TAKEN) == 1
    assert await repo.set_status(999, TopicStatus.TAKEN) is None


@pytest.mark.asyncio
async def test_repository_skips_message_it_already_saved(fake_redis):
    repo = RedisTopicRepository(fake_redis)

    assert await repo.add(_topic(message_id=10))
    assert await repo.add(_topic(message_id=10)) is None
    assert await repo.count(TopicStatus.NEW) == 1
    assert fake_redis.ttl["topics:src:-100:10"] > 0


@pytest.mark.asyncio
async def test_quota_counts_per_day_and_expires(fake_redis):
    quota = DailyQuota(fake_redis, 2, pytz.UTC)

    assert [await quota.take(7) for _ in range(3)] == [True, True, False]
    assert await quota.take(8)
    [key] = [k for k in fake_redis.ttl if k.startswith("topics:quota:7:")]
    assert fake_redis.ttl[key] == 2 * 24 * 3600


@pytest.mark.asyncio
async def test_zero_limit_means_no_quota(fake_redis):
    quota = DailyQuota(fake_redis, 0, pytz.UTC)

    assert all([await quota.take(7) for _ in range(10)])
    assert fake_redis.values == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(("text", "refusal"), [("abc", Refusal.TOO_SHORT), ("x" * 51, Refusal.TOO_LONG)])
async def test_service_checks_length(fake_redis, text, refusal):
    result = await _service(fake_redis).suggest(_topic(text))

    assert result.refusal is refusal and result.topic is None


@pytest.mark.asyncio
async def test_service_squeezes_whitespace_and_saves(fake_redis):
    result = await _service(fake_redis).suggest(_topic("  про   гостей\n из  Питера "))

    assert result.refusal is None
    assert result.topic.text == "про гостей из Питера"
    assert result.topic.id == 1


@pytest.mark.asyncio
async def test_service_stops_at_daily_limit(fake_redis):
    service = _service(fake_redis, limit=2)

    results = [await service.suggest(_topic(f"тема номер {i}")) for i in range(3)]

    assert [r.refusal for r in results] == [None, None, Refusal.LIMIT]


@pytest.mark.asyncio
async def test_duplicate_does_not_eat_the_quota(fake_redis):
    service = _service(fake_redis, limit=2)
    await service.suggest(_topic(message_id=1))

    duplicate = await service.suggest(_topic(message_id=1))
    another = await service.suggest(_topic(message_id=2))

    assert duplicate.refusal is Refusal.DUPLICATE
    assert another.refusal is None


@pytest.mark.asyncio
async def test_anonymous_author_is_not_limited(fake_redis):
    service = _service(fake_redis, limit=1)

    results = [await service.suggest(_topic(f"тема канала {i}", user_id=None)) for i in range(3)]

    assert all(r.topic is not None for r in results)


@pytest.mark.asyncio
async def test_set_status_reports_previous_status(fake_redis):
    service = _service(fake_redis)
    saved = (await service.suggest(_topic())).topic

    change = await service.set_status(saved.id, TopicStatus.LATER)
    again = await service.set_status(saved.id, TopicStatus.LATER)

    assert change.changed and change.previous is TopicStatus.NEW
    assert not again.changed
    assert await service.set_status(999, TopicStatus.LATER) is None
