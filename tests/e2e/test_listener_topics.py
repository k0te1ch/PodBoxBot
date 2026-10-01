"""Темы от слушателей на живом боте.

Бот должен быть запущен с ``TOPICS_ENABLED=true`` и Redis, тестовый аккаунт
в ``ADMINS``. Тесты включаются переменной ``E2E_TOPICS=1``; сценарии в группе
ещё и ``E2E_TOPICS_CHAT``: группа, где есть и бот (админом), и тестовый
аккаунт, и которая совпадает с ``TOPICS_CHAT`` бота (``@username`` или
числовой id).

Лимит тем на автора (``TOPICS_DAILY_LIMIT``) у тестового бота нужно снять
(``0``): каждый прогон предлагает больше трёх тем с одного аккаунта.

Эфемерные сообщения tgtest не знает, поэтому анкета в группе проверяется
сырыми запросами Telethon (``ephemeral.*``): так видно, что бот ответил и что
ответ адресован только автору. Как это выглядит в клиенте и что видят
остальные участники, остаётся ручной проверкой (см. README).
"""

import asyncio
import os
import time

import pytest
from sagenza_tgbot_sdk.menus.callback import Action, MenuCallback
from telethon import events
from telethon.tl import functions, types

pytestmark = pytest.mark.skipif(os.getenv("E2E_TOPICS") != "1", reason="set E2E_TOPICS=1 against a bot with topics on")

NEW_TOPICS = MenuCallback(m="topics", a=Action.SELECT, v="new").pack()


def _topics_chat() -> int | str:
    """Группа тем из ``E2E_TOPICS_CHAT``; без неё сценарий пропускается."""
    group = os.getenv("E2E_TOPICS_CHAT")
    if not group:
        pytest.skip("E2E_TOPICS_CHAT not set")
    # Telethon ищет строку как @username или телефон, числовой id ему нужен числом.
    return int(group) if group.lstrip("-").isdigit() else group


async def _open_topics(chat, phrase) -> None:
    await chat.command("admin")
    await chat.expect(buttons=[phrase("admin_topics", full=True)])
    await chat.click(phrase("admin_topics", full=True))
    await chat.expect_edit(contains=phrase("topics_panel"), timeout=10)


async def _open_new_topics(chat, phrase) -> None:
    await _open_topics(chat, phrase)
    await chat.click(data=NEW_TOPICS)
    await chat.expect_edit(contains=phrase("topics_entries"), timeout=10)


async def _suggest_in_private(chat, phrase, command: str, topic: str) -> None:
    await chat.command(command)
    await chat.expect(contains=phrase("topics_form_ask"))
    await chat.send(topic)
    await chat.wait_until(contains=topic, timeout=10)
    await chat.click(phrase("de-button-confirm", full=True))
    await chat.wait_until(contains=phrase("topics_form_accepted"), timeout=10)


class _EphemeralInbox:
    """Эфемерные сообщения бота тестовому аккаунту.

    В историю чата они не попадают, Telethon отдаёт их только сырыми
    апдейтами: новое сообщение и правку уже показанного.
    """

    def __init__(self, client) -> None:
        self._client = client
        self._queue: asyncio.Queue = asyncio.Queue()

    async def _on_update(self, update) -> None:
        if not update.message.out:
            await self._queue.put(update.message)

    async def __aenter__(self) -> "_EphemeralInbox":
        kinds = [types.UpdateNewEphemeralMessage, types.UpdateEditEphemeralMessage]
        self._client.add_event_handler(self._on_update, events.Raw(types=kinds))
        return self

    async def __aexit__(self, *_exc) -> None:
        self._client.remove_event_handler(self._on_update)

    async def next(self, contains: str, timeout: float = 15):
        """Ближайшее эфемерное сообщение с этим текстом."""
        deadline = time.monotonic() + timeout
        seen = []
        while (left := deadline - time.monotonic()) > 0:
            try:
                message = await asyncio.wait_for(self._queue.get(), left)
            except TimeoutError:
                break
            if contains in message.message:
                return message
            seen.append(message.message)
        raise AssertionError(f"no ephemeral message with {contains!r} in {timeout}s, got {seen}")


def _button_data(message, label: str) -> bytes:
    for row in message.reply_markup.rows:
        for button in row.buttons:
            if button.text == label:
                return button.type.data
    raise AssertionError(f"no button {label!r} under the ephemeral message")


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
        # Ответ ведущему и карточка приходят новыми сообщениями: номер прислан текстом.
        await chat.expect(contains=phrase("topics_marked_taken_episode"), timeout=10)
        card = await chat.expect(contains=topic, timeout=10)
        assert "999" in card.message


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
    group = _topics_chat()
    topic = f"e2e тема из чата {int(time.time())}"
    sent = await tester.client.send_message(group, f"#тема {topic}")
    await asyncio.sleep(3)

    # Принятую тему бот отмечает реакцией.
    marked = await tester.client.get_messages(group, ids=sent.id)
    assert marked.reactions is not None and marked.reactions.results

    async with tester.conversation(bot_username) as chat:
        await _open_new_topics(chat, phrase)
        await chat.wait_until(contains=phrase("topics_entries"), timeout=10)
        await chat.click(index=0)
        await chat.expect_edit(contains=topic, timeout=10)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ephemeral_form_in_group_lands_in_admin_queue(tester, bot_username, phrase):
    group = _topics_chat()
    topic = f"e2e эфемерная тема {int(time.time())}"
    client = tester.client
    bot = await client.get_input_entity(bot_username)
    peer = await client.get_input_entity(group)

    async with _EphemeralInbox(client) as inbox:
        await client(functions.ephemeral.SendMessageRequest(receiver_id=bot, peer=peer, message="/topic"))
        form = await inbox.next(phrase("topics_form_ask"))
        await client(
            functions.ephemeral.SendMessageRequest(
                receiver_id=bot, peer=peer, message=topic, reply_to=types.InputReplyToEphemeralMessage(id=form.id)
            )
        )
        confirm = await inbox.next(topic)
        send = _button_data(confirm, phrase("de-button-confirm", full=True))
        await client(functions.ephemeral.GetCallbackAnswerRequest(peer=peer, id=confirm.id, data=send))
        await inbox.next(phrase("topics_form_accepted"))

    async with tester.conversation(bot_username) as chat:
        await _open_new_topics(chat, phrase)
        await chat.click(index=0)
        await chat.expect_edit(contains=topic, timeout=10)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_poll_of_three_topics_is_closed_by_the_host(tester, bot_username, phrase):
    group = _topics_chat()
    client = tester.client
    stamp = int(time.time())
    for index in range(3):
        await client.send_message(group, f"#тема e2e опрос {index} {stamp}")
        await asyncio.sleep(1)
    await asyncio.sleep(3)
    before = (await client.get_messages(group, limit=1))[0].id

    async with tester.conversation(bot_username) as chat:
        await _open_topics(chat, phrase)
        await chat.click(phrase("topics_polls_button", full=True))
        await chat.expect_edit(contains=phrase("topics_polls"), timeout=10)
        await chat.click(phrase("topics_poll_new", full=True))
        await chat.expect_edit(contains=phrase("topics_poll_pick"), timeout=10)
        # Выбор хранится между заходами: начинаем с пустого.
        await chat.click(phrase("topics_poll_clear", full=True))
        await asyncio.sleep(1)
        # Свежие темы сверху: отмечаем три последние, порядок в опросе тот же.
        for index in range(3):
            await chat.click(index=index)
            await chat.expect_edit(timeout=10)
        await chat.click(phrase("topics_poll_publish", full=True))
        await chat.expect_edit(timeout=10)
        # Первая кнопка подтверждения: «Да».
        await chat.click(index=0)
        await chat.expect_edit(contains=phrase("topics_polls"), timeout=15)

        published = [m for m in await client.get_messages(group, limit=5) if m.id > before and m.poll is not None]
        assert published, "the poll did not show up in the topics chat"
        poll = published[0]
        answers = poll.poll.poll.answers
        assert len(answers) == 3
        await client(functions.messages.SendVoteRequest(peer=group, msg_id=poll.id, options=[answers[1].option]))
        await asyncio.sleep(3)

        # Свежее голосование первое в списке.
        await chat.click(index=0)
        await chat.expect_edit(contains=f"e2e опрос 1 {stamp}", timeout=10)
        await chat.click(phrase("topics_poll_close", full=True))
        # Автор победившей темы здесь тот же аккаунт: сначала уведомление ему, потом итог ведущим.
        notice = await chat.expect(contains=phrase("suggest-notify-taken"), timeout=20)
        assert f"e2e опрос 1 {stamp}" in notice.message
        result = await chat.expect(timeout=10)
        assert f"e2e опрос 1 {stamp}" in result.message

    closed = await client.get_messages(group, ids=poll.id)
    assert closed.poll.poll.closed
