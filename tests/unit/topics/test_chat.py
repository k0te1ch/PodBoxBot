"""Сбор из чата: хештеги ``#тема`` и ``#вопрос``, добавление админом по ответу."""

from unittest.mock import MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandObject
from aiogram.methods import SendMessage

import config
from handlers import topics_handler as th
from services.i18n import t
from services.topics import Kind, Source
from services.topics.runtime import is_admin, is_hosts_chat, is_topics_chat, message_link, topic_list


def _bad_request():
    return TelegramBadRequest(method=SendMessage(chat_id=1, text="x"), message="EPHEMERAL_NOT_ALLOWED")


async def _items():
    return await topic_list().repository.items()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "kind", "saved"),
    [
        ("#Тема как вы выбираете гостей?", Kind.TOPIC, "как вы выбираете гостей?"),
        ("Почему небо голубое? #вопрос", Kind.QUESTION, "Почему небо голубое?"),
        ("#вопрос #тема а что важнее?", Kind.QUESTION, "а что важнее?"),
    ],
)
async def test_hashtag_message_goes_to_the_list_with_its_kind(fake_redis, bot, group_message, text, kind, saved):
    msg = group_message(text)
    metrics = MagicMock()

    await th.collect_from_chat(msg, bot, th._hashtag_kind(msg)["kind"], metrics)

    [item] = await _items()
    assert (item.kind, item.text, item.source) == (kind, saved, Source.HASHTAG)
    assert (item.author.name, item.author.user_id) == ("@listener", 7)
    assert item.link == "https://t.me/test_group/100"
    metrics.event.assert_called_once_with("topic_added", kind=kind.value, source="hashtag")


@pytest.mark.asyncio
async def test_author_gets_both_a_reaction_and_an_ephemeral_note(fake_redis, bot, group_message):
    msg = group_message("#вопрос почему птицы летают?")

    await th.collect_from_chat(msg, bot, Kind.QUESTION)

    [reaction] = msg.react.await_args.args[0]
    assert reaction.emoji == "👍"
    note = bot.send_message.await_args.kwargs
    assert note["text"] == t("topics_added_question")
    assert note["ephemeral_message_parameters"].receiver_user_id == 7
    assert note["reply_parameters"].message_id == 100


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setting", "reacted", "noted"), [("TOPICS_ACK_REACTION", False, True), ("TOPICS_ACK_EPHEMERAL", True, False)]
)
async def test_each_acknowledgement_can_be_turned_off(
    fake_redis, bot, group_message, monkeypatch, setting, reacted, noted
):
    monkeypatch.setattr(config, setting, False)
    msg = group_message("#тема про отпуск на море")

    await th.collect_from_chat(msg, bot, Kind.TOPIC)

    assert len(await _items()) == 1
    assert msg.react.await_count == int(reacted)
    assert bot.send_message.await_count == int(noted)


def test_hashtags_are_configurable(group_message, monkeypatch):
    monkeypatch.setattr(config, "TOPICS_HASHTAGS", ["идея", "topic"])
    monkeypatch.setattr(config, "TOPICS_QUESTION_HASHTAGS", [])

    assert th._hashtag_kind(group_message("#Topic про кино")) == {"kind": Kind.TOPIC}
    assert th._hashtag_kind(group_message("#идея про кино")) == {"kind": Kind.TOPIC}
    assert th._hashtag_kind(group_message("#тема про кино")) is False
    assert th._hashtag_kind(group_message("#вопрос а почему?")) is False


def test_commands_and_plain_messages_are_not_collected(group_message):
    assert th._hashtag_kind(group_message("просто болтаю")) is False
    assert not th._not_command(group_message("/topic #тема про кино"))
    assert th._not_command(group_message("#тема про кино"))


@pytest.mark.asyncio
async def test_over_the_limit_author_gets_ephemeral_refusal(fake_redis, bot, group_message):
    for index in range(2):
        await th.collect_from_chat(group_message(f"#тема идея номер {index}", message_id=index), bot, Kind.TOPIC)
    over = group_message("#вопрос а ещё один можно?", message_id=9)
    metrics = MagicMock()

    await th.collect_from_chat(over, bot, Kind.QUESTION, metrics)

    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["text"] == t("topics_refused_limit", limit=2)
    assert kwargs["reply_parameters"].message_id == 9
    over.react.assert_not_awaited()
    assert len(await _items()) == 2
    metrics.event.assert_called_once_with("topic_refused", reason="limit")


@pytest.mark.asyncio
async def test_banned_author_gets_ephemeral_refusal(fake_redis, bot, group_message):
    await topic_list().repository.ban(7, "@listener")

    await th.collect_from_chat(group_message("#тема а можно мне?"), bot, Kind.TOPIC)

    assert bot.send_message.await_args.kwargs["text"] == t("topics_refused_banned")
    assert await _items() == []


@pytest.mark.asyncio
async def test_too_short_message_is_refused(fake_redis, bot, group_message):
    await th.collect_from_chat(group_message("#тема ой"), bot, Kind.TOPIC)

    assert bot.send_message.await_args.kwargs["text"] == t("topics_refused_too_short", min=5)


@pytest.mark.asyncio
async def test_repeated_update_is_ignored_silently(fake_redis, bot, group_message):
    await th.collect_from_chat(group_message("#тема про отпуск на море"), bot, Kind.TOPIC)
    bot.send_message.reset_mock()
    again = group_message("#тема про отпуск на море")

    await th.collect_from_chat(again, bot, Kind.TOPIC)

    assert len(await _items()) == 1
    again.react.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_channel_post_is_collected_without_a_private_note(fake_redis, bot, group_message):
    msg = group_message("#тема анонс от имени канала", user_id=None)

    await th.collect_from_chat(msg, bot, Kind.TOPIC)

    [item] = await _items()
    assert (item.author.name, item.author.user_id) == ("Podcast channel", None)
    msg.react.assert_awaited_once()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_reaction_does_not_lose_the_item(fake_redis, bot, group_message):
    msg = group_message("#тема про отпуск на море")
    msg.react.side_effect = _bad_request()

    await th.collect_from_chat(msg, bot, Kind.TOPIC)

    assert len(await _items()) == 1


# --- админ отвечает на сообщение командой ------------------------------------


def _command(name: str, args: str | None = None) -> CommandObject:
    return CommandObject(prefix="/", command=name, args=args)


def _admin_reply(group_message, text: str, target):
    return group_message(text, user_id=1, username="admin", message_id=200, reply_to=target)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "kind"),
    [("вопрос", Kind.QUESTION), ("question", Kind.QUESTION), ("тема", Kind.TOPIC), ("Topic", Kind.TOPIC)],
)
async def test_admin_takes_a_chat_message_by_replying(fake_redis, bot, group_message, command, kind):
    target = group_message("А расскажите, как вы познакомились", message_id=55)
    msg = _admin_reply(group_message, f"/{command}", target)
    metrics = MagicMock()

    await th.add_by_reply(msg, _command(command), bot, metrics)

    [item] = await _items()
    assert (item.kind, item.source) == (kind, Source.REPLY)
    assert item.text == "А расскажите, как вы познакомились"
    assert (item.author.name, item.author.user_id) == ("@listener", 7)
    assert (item.message_id, item.link) == (55, "https://t.me/test_group/55")
    target.react.assert_awaited_once()
    note = bot.send_message.await_args.kwargs
    assert note["ephemeral_message_parameters"].receiver_user_id == 1
    assert f"1) {t(f'topics_kind_{kind}')} - А расскажите, как вы познакомились" in note["text"]
    msg.delete.assert_awaited_once()
    metrics.event.assert_called_once_with("topic_added", kind=kind.value, source="reply")


@pytest.mark.asyncio
async def test_admin_reply_ignores_limit_ban_and_length(fake_redis, bot, group_message):
    await topic_list().repository.ban(7, "@listener")
    target = group_message("Юг?", message_id=55)

    await th.add_by_reply(_admin_reply(group_message, "/вопрос", target), _command("вопрос"), bot)

    [item] = await _items()
    assert item.text == "Юг?"


@pytest.mark.asyncio
async def test_text_after_the_command_replaces_the_message_text(fake_redis, bot, group_message):
    target = group_message("ну вот мы тут с женой съездили, такое было, расскажу потом", message_id=55)

    await th.add_by_reply(
        _admin_reply(group_message, "/тема Как съездили в отпуск", target),
        _command("тема", "Как съездили в отпуск"),
        bot,
    )

    [item] = await _items()
    assert (item.text, item.message_id) == ("Как съездили в отпуск", 55)


@pytest.mark.asyncio
async def test_hashtags_are_cut_from_the_replied_message(fake_redis, bot, group_message):
    target = group_message("#вопрос почему небо голубое?", message_id=55)

    await th.add_by_reply(_admin_reply(group_message, "/вопрос", target), _command("вопрос"), bot)

    [item] = await _items()
    assert item.text == "почему небо голубое?"


@pytest.mark.asyncio
async def test_message_already_on_the_list_is_not_added_twice(fake_redis, bot, group_message):
    target = group_message("#тема про отпуск на море", message_id=55)
    await th.collect_from_chat(target, bot, Kind.TOPIC)
    bot.send_message.reset_mock()

    await th.add_by_reply(_admin_reply(group_message, "/тема", target), _command("тема"), bot)

    assert len(await _items()) == 1
    assert bot.send_message.await_args.kwargs["text"] == t("topics_refused_duplicate")


@pytest.mark.asyncio
async def test_reply_to_a_message_without_text_explains_itself(fake_redis, bot, group_message):
    target = group_message(None, message_id=55)

    await th.add_by_reply(_admin_reply(group_message, "/тема", target), _command("тема"), bot)

    assert await _items() == []
    assert bot.send_message.await_args.kwargs["text"] == t("topics_reply_no_text")
    target.react.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_is_answered_in_private_when_ephemeral_fails(fake_redis, bot, group_message):
    bot.send_message.side_effect = [_bad_request(), None]
    target = group_message("А расскажите, как вы познакомились", message_id=55)

    await th.add_by_reply(_admin_reply(group_message, "/тема", target), _command("тема"), bot)

    private = bot.send_message.await_args.kwargs
    assert private["chat_id"] == 1
    assert "ephemeral_message_parameters" not in private


@pytest.mark.asyncio
async def test_ephemeral_command_is_not_deleted(fake_redis, bot, group_message):
    target = group_message("А расскажите, как вы познакомились", message_id=55)
    msg = group_message("/тема", user_id=1, username="admin", reply_to=target, ephemeral_id=9)

    await th.add_by_reply(msg, _command("тема"), bot)

    msg.delete.assert_not_awaited()


def test_only_real_replies_count(group_message):
    target = group_message("сообщение", message_id=55)
    assert th._is_reply(_admin_reply(group_message, "/тема", target))
    assert not th._is_reply(group_message("/тема"))
    # В форуме сообщение темы «отвечает» на служебное сообщение о её создании.
    target.forum_topic_created = MagicMock()
    assert not th._is_reply(_admin_reply(group_message, "/тема", target))


def test_only_admins_add_by_reply(group_message):
    assert is_admin(group_message("/тема", username="admin"))
    assert not is_admin(group_message("/тема", username="listener"))
    assert not is_admin(group_message("/тема", user_id=None))


# --- чаты ---------------------------------------------------------------------


def test_topics_chat_is_matched_by_username_or_id(group_message, monkeypatch):
    chat = group_message("x").chat
    assert is_topics_chat(chat)
    monkeypatch.setattr(config, "TOPICS_CHAT", "-1001234567890")
    assert is_topics_chat(chat)
    monkeypatch.setattr(config, "TOPICS_CHAT", "@other")
    assert not is_topics_chat(chat)


def test_hosts_chat_is_off_by_default_and_never_the_topics_chat(group_message, monkeypatch):
    chat = group_message("x").chat
    assert not is_hosts_chat(chat)
    monkeypatch.setattr(config, "TOPICS_HOSTS_CHAT", "@test_group")
    assert not is_hosts_chat(chat)
    monkeypatch.setattr(config, "TOPICS_CHAT", "@listeners")
    assert is_hosts_chat(chat)


def test_message_link_for_public_and_private_groups(group_message):
    chat = group_message("x").chat
    assert message_link(chat, 5) == "https://t.me/test_group/5"
    chat.username = None
    assert message_link(chat, 5) == "https://t.me/c/1234567890/5"
    chat.id = -42
    assert message_link(chat, 5) is None
