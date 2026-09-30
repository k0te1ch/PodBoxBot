"""Вариант A: «#тема» в чате, ответ автору и уведомление о статусе."""

from unittest.mock import MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendMessage

import config
from handlers import topics_handler as th
from services.i18n import t
from services.topics import Author, Topic, TopicSource, TopicStatus
from services.topics.delivery import notify_author
from services.topics.runtime import is_topics_chat, message_link, topic_service


def _forbidden():
    return TelegramForbiddenError(method=SendMessage(chat_id=1, text="x"), message="bot can't initiate conversation")


@pytest.mark.asyncio
async def test_hashtag_message_becomes_topic_with_reaction(fake_redis, bot, group_message):
    msg = group_message("#Тема как вы выбираете гостей?")
    metrics = MagicMock()

    await th.collect_from_chat(msg, bot, metrics)

    [topic] = await topic_service().repository.list(TopicStatus.NEW)
    assert topic.text == "как вы выбираете гостей?"
    assert (topic.author.name, topic.author.user_id) == ("@listener", 7)
    assert topic.link == "https://t.me/test_group/100"
    assert topic.source is TopicSource.HASHTAG
    msg.react.assert_awaited_once()
    metrics.event.assert_called_once_with("topic_suggested", source=TopicSource.HASHTAG)
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_over_the_limit_author_gets_ephemeral_reply(fake_redis, bot, group_message):
    for i in range(2):
        await th.collect_from_chat(group_message(f"#тема идея номер {i}", message_id=i), bot)

    await th.collect_from_chat(group_message("#тема ещё одна идея", message_id=9), bot)

    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["ephemeral_message_parameters"].receiver_user_id == 7
    assert kwargs["reply_parameters"].message_id == 9
    assert kwargs["text"] == t("topics_refused_limit", limit=2)
    assert await topic_service().repository.count(TopicStatus.NEW) == 2


@pytest.mark.asyncio
async def test_too_short_topic_is_explained(fake_redis, bot, group_message):
    await th.collect_from_chat(group_message("#тема а?"), bot)

    assert bot.send_message.await_args.kwargs["text"] == t("topics_refused_too_short", min=5)


@pytest.mark.asyncio
async def test_repeated_update_is_ignored_silently(fake_redis, bot, group_message):
    await th.collect_from_chat(group_message("#тема про музыку в эфире"), bot)
    again = group_message("#тема про музыку в эфире")

    await th.collect_from_chat(again, bot)

    again.react.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_channel_post_is_saved_without_author_id(fake_redis, bot, group_message):
    await th.collect_from_chat(group_message("#тема от имени канала", user_id=None), bot)

    [topic] = await topic_service().repository.list(TopicStatus.NEW)
    assert topic.author == Author(name="Podcast channel")


@pytest.mark.asyncio
async def test_reaction_failure_does_not_lose_topic(fake_redis, bot, group_message):
    msg = group_message("#тема без реакций в чате")
    msg.react.side_effect = TelegramBadRequest(method=SendMessage(chat_id=1, text="x"), message="REACTION_INVALID")

    await th.collect_from_chat(msg, bot)

    assert await topic_service().repository.count(TopicStatus.NEW) == 1


def test_filters_match_chat_hashtag_and_flag(monkeypatch, group_message):
    msg = group_message("#тема что-то")
    assert th._from_topics_chat(msg) and th._has_topic_hashtag(msg)
    assert not th._has_topic_hashtag(group_message("#вопрос что-то"))

    monkeypatch.setattr(config, "TOPICS_HASHTAG", "")
    assert not th._has_topic_hashtag(msg)

    monkeypatch.setattr(config, "TOPICS_ENABLED", False)
    assert not th.topics_enabled(msg)


def test_topics_chat_can_be_numeric_id(monkeypatch, group_message):
    chat = group_message("x").chat
    monkeypatch.setattr(config, "TOPICS_CHAT", "-1001234567890")
    assert is_topics_chat(chat)
    monkeypatch.setattr(config, "TOPICS_CHAT", "@other")
    assert not is_topics_chat(chat)


def test_private_supergroup_link(group_message):
    chat = group_message("x").chat
    chat.username = None

    assert message_link(chat, 5) == "https://t.me/c/1234567890/5"


def _saved_topic(user_id=7) -> Topic:
    return Topic(
        text="тема <b>с разметкой</b>",
        author=Author(name="@listener", user_id=user_id),
        source=TopicSource.HASHTAG,
        status=TopicStatus.TAKEN,
        id=1,
        chat_id=-100,
    )


@pytest.mark.asyncio
async def test_status_notice_goes_to_private_chat_first(bot):
    assert await th.notify_status(bot, _saved_topic())

    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 7
    assert kwargs["text"] == t("topics_notice_taken", topic="тема &lt;b&gt;с разметкой&lt;/b&gt;")


@pytest.mark.asyncio
async def test_status_notice_falls_back_to_ephemeral_in_group(bot):
    bot.send_message.side_effect = [_forbidden(), None]

    assert await notify_author(bot, _saved_topic(), "текст")

    fallback = bot.send_message.await_args_list[1].kwargs
    assert fallback["chat_id"] == -100
    assert fallback["ephemeral_message_parameters"].receiver_user_id == 7


@pytest.mark.asyncio
async def test_status_notice_gives_up_quietly(bot):
    bot.send_message.side_effect = _forbidden()

    assert not await notify_author(bot, _saved_topic(), "текст")
    assert not await notify_author(bot, _saved_topic(user_id=None), "текст")
