"""Очередь тем поверх модуля suggest SDK: адаптер, лимит, бан-лист и проверки сервиса."""

from unittest.mock import MagicMock

import pytest
from sagenza_tgbot_sdk.suggest import SuggestionStatus

from services.topics import Author, Refusal, SuggestTopicRepository, Topic, TopicSource, TopicStatus, runtime
from services.topics.runtime import QUEUE_PREFIX, topic_service


def _topic(text="обсудить подкасты про кино", user_id=7, message_id=None) -> Topic:
    return Topic(
        text=text,
        author=Author(name="@listener", user_id=user_id),
        source=TopicSource.HASHTAG,
        chat_id=-100 if message_id else None,
        message_id=message_id,
        link="https://t.me/test_group/5" if message_id else None,
    )


def _repo(fake_redis) -> SuggestTopicRepository:
    return SuggestTopicRepository(runtime.suggestion_box(), fake_redis)


def test_topic_statuses_are_the_sdk_ones():
    assert TopicStatus is SuggestionStatus
    assert [status.value for status in TopicStatus] == ["new", "taken", "rejected", "later"]


@pytest.mark.asyncio
async def test_topic_round_trips_through_the_sdk_queue(fake_redis):
    repo = _repo(fake_redis)

    saved = await repo.add(_topic(message_id=5))
    restored = await repo.get(saved.id)

    assert restored == saved
    assert (restored.id, restored.chat_id, restored.message_id) == (1, -100, 5)
    assert restored.author == Author(name="@listener", user_id=7, language="ru")
    assert restored.source is TopicSource.HASHTAG
    assert await fake_redis.exists(f"{QUEUE_PREFIX}:item:1")


@pytest.mark.asyncio
async def test_repository_lists_by_status_newest_first(fake_redis):
    repo = _repo(fake_redis)
    first = await repo.add(_topic("первая тема", user_id=1))
    second = await repo.add(_topic("вторая тема", user_id=2))
    third = await repo.add(_topic("третья тема", user_id=3))

    assert [t.text for t in await repo.list(TopicStatus.NEW)] == ["третья тема", "вторая тема", "первая тема"]
    assert [t.id for t in await repo.list(TopicStatus.NEW, limit=2)] == [third.id, second.id]

    moved = await repo.set_status(first.id, TopicStatus.TAKEN, note="42", moderator_id=1)

    assert (moved.status, moved.note) == (TopicStatus.TAKEN, "42")
    assert (await repo.get(first.id)).note == "42"
    assert [t.id for t in await repo.list(TopicStatus.NEW)] == [third.id, second.id]
    assert await repo.count(TopicStatus.TAKEN) == 1
    assert await repo.set_status(999, TopicStatus.TAKEN) is None


@pytest.mark.asyncio
async def test_repository_skips_message_it_already_saved(fake_redis):
    repo = _repo(fake_redis)

    assert await repo.add(_topic(message_id=10))
    assert await repo.add(_topic(message_id=10)) is None
    assert await repo.count(TopicStatus.NEW) == 1
    assert await fake_redis.ttl("topics:src:-100:10") > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("text", "refusal"), [("abc", Refusal.TOO_SHORT), ("x" * 51, Refusal.TOO_LONG)])
async def test_service_checks_length(fake_redis, text, refusal):
    result = await topic_service().suggest(_topic(text))

    assert result.refusal is refusal and result.topic is None


@pytest.mark.asyncio
async def test_service_squeezes_whitespace_and_saves(fake_redis):
    result = await topic_service().suggest(_topic("  про   гостей\n из  Питера "))

    assert result.refusal is None
    assert result.topic.text == "про гостей из Питера"
    assert result.topic.id == 1


@pytest.mark.asyncio
async def test_service_stops_at_the_sdk_limit(fake_redis):
    service = topic_service()

    results = [await service.suggest(_topic(f"тема номер {i}")) for i in range(3)]

    assert [r.refusal for r in results] == [None, None, Refusal.LIMIT]


@pytest.mark.asyncio
async def test_zero_limit_means_no_limit(fake_redis, monkeypatch):
    import config

    monkeypatch.setattr(config, "TOPICS_DAILY_LIMIT", 0)
    service = topic_service()

    results = [await service.suggest(_topic(f"тема номер {i}")) for i in range(5)]

    assert all(r.topic is not None for r in results)


@pytest.mark.asyncio
async def test_duplicate_does_not_eat_the_limit(fake_redis):
    service = topic_service()
    await service.suggest(_topic(message_id=1))

    duplicate = await service.suggest(_topic(message_id=1))
    another = await service.suggest(_topic(message_id=2))

    assert duplicate.refusal is Refusal.DUPLICATE
    assert another.refusal is None


@pytest.mark.asyncio
async def test_anonymous_author_is_not_limited(fake_redis):
    service = topic_service()

    results = [await service.suggest(_topic(f"тема канала {i}", user_id=None)) for i in range(3)]

    assert all(r.topic is not None for r in results)
    assert results[0].topic.author.user_id is None


@pytest.mark.asyncio
async def test_banned_author_is_refused_until_unbanned(fake_redis):
    service = topic_service()
    await service.repository.ban(7)

    refused = await service.suggest(_topic("тема от забаненного"))
    await service.repository.unban(7)
    accepted = await service.suggest(_topic("тема после разбана"))

    assert refused.refusal is Refusal.BANNED
    assert accepted.topic is not None
    assert not await service.repository.is_banned(7)


@pytest.mark.asyncio
async def test_set_status_reports_previous_status_and_note(fake_redis):
    service = topic_service()
    saved = (await service.suggest(_topic())).topic

    change = await service.set_status(saved.id, TopicStatus.LATER)
    again = await service.set_status(saved.id, TopicStatus.LATER)
    taken = await service.set_status(saved.id, TopicStatus.TAKEN, note="12", moderator_id=1)

    assert change.changed and change.previous is TopicStatus.NEW
    assert not again.changed
    assert taken.changed and taken.topic.note == "12"
    assert await service.set_status(999, TopicStatus.LATER) is None


@pytest.mark.asyncio
async def test_sdk_counts_submitted_and_moderated_topics(fake_redis):
    metrics = MagicMock()
    service = topic_service(MagicMock(), metrics)

    saved = (await service.suggest(_topic())).topic
    await service.set_status(saved.id, TopicStatus.TAKEN)

    metrics.event.assert_any_call("suggestion_submitted", source="hashtag")
    metrics.event.assert_any_call("suggestion_moderated", status="taken")


@pytest.mark.asyncio
async def test_sdk_sends_no_cards_and_no_notices(fake_redis):
    """Разбор идёт в /admin бота, автору пишет бот сам: SDK молчит."""
    bot = MagicMock()
    service = topic_service(bot)

    saved = (await service.suggest(_topic())).topic
    await service.set_status(saved.id, TopicStatus.TAKEN, note="7")

    bot.send_message.assert_not_called()
    bot.edit_message_text.assert_not_called()
