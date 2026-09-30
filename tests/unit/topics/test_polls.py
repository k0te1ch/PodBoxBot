"""Вариант D: опрос по темам, голоса, закрытие и победитель."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import StopPoll
from sagenza_tgbot_sdk.menus.testing import crawl

import config
from handlers import menus
from handlers import topics_polls_handler as ph
from services.i18n import t
from services.topics import Author, PollStore, Topic, TopicPoll, TopicSource, TopicStatus
from services.topics.runtime import poll_store, topic_service


@pytest.fixture(autouse=True)
def _admin_ids(monkeypatch):
    monkeypatch.setattr(config, "ADMINS_ID", [100])


def _admin_event():
    event = MagicMock()
    event.from_user.username = "admin"
    event.from_user.language_code = "ru"
    return event


def _fsm():
    data: dict = {}
    state = MagicMock(spec=ph.FSMContext)
    state.update_data = AsyncMock(side_effect=lambda d: data.update(d))
    state.get_data = AsyncMock(side_effect=lambda: data)
    return state


def _ctx(bot=None, value=None, state=None, metrics=None):
    data = {"state": state or _fsm(), "bot": bot, "metrics": metrics}
    ctx = menus.menus.context(_admin_event(), data, locale="ru")
    ctx.value = value
    ctx.answer = AsyncMock()
    ctx.show = AsyncMock()
    ctx.put = AsyncMock()
    return ctx


async def _add(text, status=TopicStatus.NEW, created_at=1.0, user_id=7) -> Topic:
    repository = topic_service().repository
    topic = await repository.add(
        Topic(
            text=text,
            author=Author(name="@listener", user_id=user_id),
            source=TopicSource.HASHTAG,
            created_at=created_at,
        )
    )
    if status is not TopicStatus.NEW:
        topic = await repository.set_status(topic.id, status)
    return topic


def _sent_poll(poll_id="tg-poll-1"):
    message = MagicMock(message_id=55)
    message.chat.id = -1001234567890
    message.poll.id = poll_id
    return message


def _poll_update(votes, closed=False, poll_id="tg-poll-1"):
    poll = MagicMock()
    poll.id = poll_id
    poll.options = [MagicMock(voter_count=count) for count in votes]
    poll.is_closed = closed
    return poll


async def _published(bot, count=3) -> tuple[TopicPoll, list[Topic]]:
    topics = [await _add(f"тема номер {i}", created_at=float(i)) for i in range(count)]
    bot.send_poll = AsyncMock(return_value=_sent_poll())
    ctx = _ctx(bot)
    for topic in topics:
        ctx.value = str(topic.id)
        await ph._toggle(ctx)
    await ph.publish(ctx)
    [poll] = await poll_store().list()
    return poll, topics


def test_leader_prefers_first_on_tie_and_needs_votes():
    poll = TopicPoll(topic_ids=[1, 2, 3], options=["a", "b", "c"], chat_id=1, message_id=1, poll_id="p")
    assert poll.leader() is None
    poll.votes = [0, 0, 0]
    assert poll.leader() is None and not poll.is_tie()
    poll.votes = [2, 5, 5]
    assert poll.leader() == 1 and poll.is_tie()
    assert TopicPoll.from_json(poll.to_json()) == poll


@pytest.mark.asyncio
async def test_store_finds_poll_by_telegram_id_and_closes_once(fake_redis):
    store = PollStore(fake_redis)
    first = await store.add(TopicPoll([1], ["a"], chat_id=1, message_id=1, poll_id="x", created_at=1))
    second = await store.add(TopicPoll([2], ["b"], chat_id=1, message_id=2, poll_id="y", created_at=2))

    assert (await store.by_telegram_id("x")).id == first.id
    assert await store.by_telegram_id("nope") is None
    assert [p.id for p in await store.list()] == [second.id, first.id]
    assert await store.claim_close(first.id)
    assert not await store.claim_close(first.id)


@pytest.mark.asyncio
async def test_pick_list_offers_new_and_postponed_topics_with_marks(fake_redis):
    new = await _add("новая тема", created_at=2)
    later = await _add("отложенная тема", TopicStatus.LATER, created_at=1)
    await _add("уже взятая тема", TopicStatus.TAKEN, created_at=3)
    ctx = _ctx(value=str(later.id))

    await ph._toggle(ctx)
    items = await ph._pick_items(ctx)

    assert [(i.id, i.text) for i in items] == [(str(new.id), "▫️ новая тема"), (str(later.id), "☑️ отложенная тема")]
    ctx.show.assert_awaited_once_with(ph.PICK_MENU, 0)

    await ph._toggle(ctx)
    assert await ph._picked(ctx) == []


@pytest.mark.asyncio
async def test_pick_stops_at_five(fake_redis):
    topics = [await _add(f"тема номер {i}") for i in range(6)]
    ctx = _ctx()
    for topic in topics:
        ctx.value = str(topic.id)
        await ph._toggle(ctx)

    assert len(await ph._picked(ctx)) == 5
    ctx.answer.assert_awaited_once_with(t("topics_poll_too_many", max=5), alert=True)


@pytest.mark.asyncio
async def test_publish_needs_three_topics(fake_redis, bot):
    bot.send_poll = AsyncMock()
    ctx = _ctx(bot)
    ctx.value = str((await _add("одна тема")).id)
    await ph._toggle(ctx)

    await ph.publish(ctx)

    bot.send_poll.assert_not_awaited()
    ctx.answer.assert_awaited_with(t("topics_poll_pick_count", min=3, max=5), alert=True)


@pytest.mark.asyncio
async def test_publish_sends_anonymous_poll_and_remembers_it(fake_redis, bot):
    metrics = MagicMock()
    topics = [await _add(f"тема номер {i}" + "!" * 120 * (i == 0)) for i in range(3)]
    bot.send_poll = AsyncMock(return_value=_sent_poll())
    ctx = _ctx(bot, metrics=metrics)
    for topic in topics:
        ctx.value = str(topic.id)
        await ph._toggle(ctx)

    await ph.publish(ctx)

    kwargs = bot.send_poll.await_args.kwargs
    assert kwargs["chat_id"] == "@test_group"
    assert kwargs["is_anonymous"] and kwargs["open_period"] == 24 * 3600
    assert [len(o.text) <= 100 for o in kwargs["options"]] == [True] * 3
    [poll] = await poll_store().list()
    assert (poll.topic_ids, poll.poll_id, poll.votes) == ([t.id for t in topics], "tg-poll-1", [0, 0, 0])
    assert await ph._picked(ctx) == []
    metrics.event.assert_called_once_with("topic_poll", action="published")
    ctx.show.assert_awaited_with(ph.POLLS_MENU)


@pytest.mark.asyncio
async def test_zero_hours_means_no_auto_close(fake_redis, bot, monkeypatch):
    monkeypatch.setattr(config, "TOPICS_POLL_HOURS", 0)

    await _published(bot)

    assert bot.send_poll.await_args.kwargs["open_period"] is None


@pytest.mark.asyncio
async def test_votes_are_tracked_and_closed_poll_picks_winner(fake_redis, bot):
    poll, topics = await _published(bot)
    metrics = MagicMock()

    await ph.on_poll_update(_poll_update([1, 4, 2]), bot, metrics)
    assert (await poll_store().get(poll.id)).votes == [1, 4, 2]
    bot.send_message.assert_not_awaited()

    await ph.on_poll_update(_poll_update([1, 6, 2], closed=True), bot, metrics)

    stored = await poll_store().get(poll.id)
    assert stored.closed and stored.winner_id == topics[1].id and stored.votes == [1, 6, 2]
    assert (await topic_service().repository.get(topics[1].id)).status is TopicStatus.TAKEN
    recipients = [call.kwargs["chat_id"] for call in bot.send_message.await_args_list]
    assert recipients == [7, 100]
    assert "тема номер 1" in bot.send_message.await_args.kwargs["text"]
    metrics.event.assert_any_call("topic_status", status=TopicStatus.TAKEN)
    metrics.event.assert_any_call("topic_poll", action="closed")

    await ph.on_poll_update(_poll_update([1, 7, 2], closed=True), bot, metrics)
    assert (await poll_store().get(poll.id)).votes == [1, 6, 2]


@pytest.mark.asyncio
async def test_poll_without_votes_has_no_winner(fake_redis, bot):
    poll, _topics = await _published(bot)

    await ph.on_poll_update(_poll_update([0, 0, 0], closed=True), bot)

    assert (await poll_store().get(poll.id)).winner_id is None
    assert await topic_service().repository.count(TopicStatus.TAKEN) == 0
    assert bot.send_message.await_args.kwargs["text"] == t("topics_poll_result_none", id=poll.id)


@pytest.mark.asyncio
async def test_unknown_poll_update_is_ignored(fake_redis, bot):
    await ph.on_poll_update(_poll_update([3], closed=True, poll_id="someone-else"), bot)

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_closes_poll_with_stop_poll(fake_redis, bot):
    poll, topics = await _published(bot)
    bot.stop_poll = AsyncMock(return_value=_poll_update([3, 1, 0], closed=True))
    ctx = _ctx(bot)

    with patch.object(menus.menus, "context", return_value=ctx):
        await ph.close_poll(MagicMock(), ph.PollCallback(a="close", id=poll.id), MagicMock(), bot)

    bot.stop_poll.assert_awaited_once_with(chat_id=poll.chat_id, message_id=poll.message_id)
    assert (await poll_store().get(poll.id)).winner_id == topics[0].id
    text, markup = ctx.put.await_args.args
    assert "🏆" in text
    assert len(markup.inline_keyboard) == 1


@pytest.mark.asyncio
async def test_close_uses_last_votes_when_poll_already_stopped(fake_redis, bot):
    poll, topics = await _published(bot)
    await ph.on_poll_update(_poll_update([0, 0, 2]), bot)
    bot.stop_poll = AsyncMock(
        side_effect=TelegramBadRequest(
            method=StopPoll(chat_id=1, message_id=1), message="poll has already been closed"
        )
    )

    with patch.object(menus.menus, "context", return_value=_ctx(bot)):
        await ph.close_poll(MagicMock(), ph.PollCallback(a="close", id=poll.id), MagicMock(), bot)

    assert (await poll_store().get(poll.id)).winner_id == topics[2].id


@pytest.mark.asyncio
async def test_poll_card_and_list_show_result(fake_redis, bot):
    poll, _topics = await _published(bot)
    await ph.on_poll_update(_poll_update([2, 2, 0], closed=True), bot)
    ctx = _ctx(bot, value=str(poll.id))

    items = await ph._poll_items(ctx)
    await ph._open_poll(ctx)

    assert items[0].text.startswith("🏁") and "тема номер 0" in items[0].text
    text, markup = ctx.put.await_args.args
    assert t("topics_poll_tie") in text
    assert "🏆 тема номер 0" in text


@pytest.mark.asyncio
async def test_poll_menus_open_in_crawl(fake_redis, bot):
    await _published(bot)

    report = await crawl(menus.menus, menus.menus.context(_admin_event(), locale="ru"), locales=["ru", "en"])

    report.raise_for_problems()
    assert {"topics_polls@0", "topics_poll_pick@0"} <= set(report.opened)
    assert {"topics_poll_pick/publish", "topics_poll_pick/clear"} <= set(report.pressed)
