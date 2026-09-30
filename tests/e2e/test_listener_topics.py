"""Темы от слушателей на живом боте.

Бот должен быть запущен с ``TOPICS_ENABLED=true`` и Redis, тестовый аккаунт
в ``ADMINS``. Тесты включаются переменной ``E2E_TOPICS=1``; сценарий с
хештегом ещё и ``E2E_TOPICS_CHAT``: группа, где есть и бот (админом), и
тестовый аккаунт, и которая совпадает с ``TOPICS_CHAT`` бота.

Лимит тем на автора (``TOPICS_DAILY_LIMIT``) у тестового бота лучше снять
(``0``): сценарии предлагают по теме за прогон.

Эфемерную анкету в группе отсюда не проверить: Telethon-клиент не отличает
эфемерные сообщения, это остаётся ручной проверкой (см. README).
"""

import asyncio
import os
import time

import pytest
from sagenza_tgbot_sdk.menus.callback import Action, MenuCallback

pytestmark = pytest.mark.skipif(os.getenv("E2E_TOPICS") != "1", reason="set E2E_TOPICS=1 against a bot with topics on")

NEW_TOPICS = MenuCallback(m="topics", a=Action.SELECT, v="new").pack()


async def _open_new_topics(chat, phrase) -> None:
    await chat.command("admin")
    await chat.expect(buttons=[phrase("admin_topics", full=True)])
    await chat.click(phrase("admin_topics", full=True))
    await chat.expect_edit(contains=phrase("topics_panel"), timeout=10)
    await chat.click(data=NEW_TOPICS)
    await chat.expect_edit(contains=phrase("topics_entries"), timeout=10)


async def _suggest_in_private(chat, phrase, command: str, topic: str) -> None:
    await chat.command(command)
    await chat.expect(contains=phrase("topics_form_ask"))
    await chat.send(topic)
    await chat.wait_until(contains=topic, timeout=10)
    await chat.click(phrase("de-button-confirm", full=True))
    await chat.wait_until(contains=phrase("topics_form_accepted"), timeout=10)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_private_form_topic_is_taken_into_episode_and_author_notified(tester, bot_username, phrase):
    topic = f"e2e тема про гостей {int(time.time())}"
    async with tester.conversation(bot_username) as chat:
        await _suggest_in_private(chat, phrase, "start topic", topic)

    async with tester.conversation(bot_username) as chat:
        await _open_new_topics(chat, phrase)
        # Свежая тема первая в списке.
        await chat.click(index=0)
        await chat.expect_edit(contains=topic, timeout=10)
        await chat.click(phrase("topics_take", full=True))
        await chat.expect_edit(contains=phrase("topics_ask_episode"), timeout=10)
        await chat.send("999")
        # Автор здесь тот же аккаунт: уведомление приходит раньше ответа ведущему.
        notice = await chat.expect(contains=phrase("suggest-notify-taken-note"), timeout=20)
        assert topic[:20] in notice.message
        assert "999" in notice.message
        await chat.wait_until(contains=phrase("topics_marked_taken_episode"), timeout=10)


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["topic", "тема"])
async def test_private_command_opens_the_same_form(tester, bot_username, phrase, command):
    topic = f"e2e тема по команде {command} {int(time.time())}"
    async with tester.conversation(bot_username) as chat:
        await _suggest_in_private(chat, phrase, command, topic)

    async with tester.conversation(bot_username) as chat:
        await _open_new_topics(chat, phrase)
        await chat.click(index=0)
        await chat.expect_edit(contains=topic, timeout=10)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_hashtag_in_group_lands_in_admin_queue(tester, bot_username, phrase):
    group = os.getenv("E2E_TOPICS_CHAT")
    if not group:
        pytest.skip("E2E_TOPICS_CHAT not set")
    topic = f"e2e тема из чата {int(time.time())}"
    await tester.client.send_message(group, f"#тема {topic}")
    await asyncio.sleep(3)

    async with tester.conversation(bot_username) as chat:
        await _open_new_topics(chat, phrase)
        await chat.wait_until(contains=phrase("topics_entries"), timeout=10)
        await chat.click(index=0)
        await chat.expect_edit(contains=topic, timeout=10)
