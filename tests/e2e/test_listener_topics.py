"""Список тем и вопросов от слушателей на живом боте.

Бот должен быть запущен с ``TOPICS_ENABLED=true`` и Redis, тестовый аккаунт
в ``ADMINS``. Тесты включаются переменной ``E2E_TOPICS=1``; сценарии в группе
ещё и ``E2E_TOPICS_CHAT``: группа, где есть и бот (админом), и тестовый
аккаунт, и которая совпадает с ``TOPICS_CHAT`` бота (``@username`` или
числовой id).

Тестовый аккаунт админ, поэтому лимит на автора и бан его не касаются: эти
отказы проверяются unit-тестами и вручную, вторым аккаунтом.

Список у бота один и общий, поэтому каждый тест ищет свои пункты по тексту с
меткой времени и в конце удаляет их.

Эфемерные сообщения tgtest не знает, поэтому анкета в группе проверяется
сырыми запросами Telethon (``ephemeral.*``): так видно, что бот ответил и что
ответ адресован только автору. Как это выглядит в клиенте и что видят
остальные участники, остаётся ручной проверкой (см. README).
"""

import asyncio
import os
import re
import time

import pytest
from telethon import events
from telethon.tl import functions, types

# Значок пункта, отмеченного к удалению: тот же, что MARK в services/topics/listing.py.
MARK = "🗑 "

pytestmark = pytest.mark.skipif(os.getenv("E2E_TOPICS") != "1", reason="set E2E_TOPICS=1 against a bot with topics on")


def _topics_chat() -> int | str:
    """Группа тем из ``E2E_TOPICS_CHAT``; без неё сценарий пропускается."""
    group = os.getenv("E2E_TOPICS_CHAT")
    if not group:
        pytest.skip("E2E_TOPICS_CHAT not set")
    # Telethon ищет строку как @username или телефон, числовой id ему нужен числом.
    return int(group) if group.lstrip("-").isdigit() else group


def _has_button(message, label: str) -> bool:
    return any(button.text == label for row in message.buttons or [] for button in row)


async def _show_list(chat, phrase):
    """``/topics``: текст всего списка и его последнее сообщение, под которым кнопки действий."""
    await chat.command("topics")
    refresh = phrase("topics_refresh", full=True)
    texts = []
    while True:
        message = await chat.get_reply(timeout=15)
        texts.append(message.message)
        if _has_button(message, refresh):
            return "\n".join(texts), message


def _number(listing: str, kind: str, text: str) -> int:
    """Номер пункта ``N) ТИП - текст`` в показанном списке."""
    found = re.search(rf"^(\d+)\) {re.escape(kind)} - {re.escape(text)}$", listing, re.MULTILINE)
    assert found, f"no line '{kind} - {text}' in the list:\n{listing}"
    return int(found.group(1))


async def _delete(chat, phrase, *lines: tuple[str, str]):
    """Удалить пункты ``(тип, текст)`` командой «удали …»; в ответе отчёт бота об удалении."""
    listing, _last = await _show_list(chat, phrase)
    numbers = [_number(listing, kind, text) for kind, text in lines]
    await chat.send("удали " + ", ".join(map(str, numbers)))
    report = await chat.expect(contains=phrase("topics_removed"), timeout=15)
    for _kind, text in lines:
        assert text in report.message
    rest = await chat.get_reply(timeout=15)
    for _kind, text in lines:
        assert text not in rest.message
    return report


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
async def test_private_commands_add_a_topic_and_a_question_to_one_list(tester, bot_username, phrase):
    stamp = int(time.time())
    topic, question = f"e2e как съездили в отпуск {stamp}", f"e2e почему небо голубое {stamp}?"
    topic_kind, question_kind = phrase("topics_kind_topic", full=True), phrase("topics_kind_question", full=True)
    async with tester.conversation(bot_username) as chat:
        await chat.command(f"тема {topic}")
        await chat.expect(contains=f"{topic_kind} - {topic}", timeout=15)
        await chat.command(f"вопрос {question}")
        await chat.expect(contains=f"{question_kind} - {question}", timeout=15)

        listing, _last = await _show_list(chat, phrase)
        assert listing.startswith(phrase("topics_list_title", full=True))
        # Пункты идут в порядке добавления, нумерация сквозная.
        assert _number(listing, question_kind, question) == _number(listing, topic_kind, topic) + 1

        await _delete(chat, phrase, (topic_kind, topic), (question_kind, question))


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_form_asks_for_the_kind_and_adds_the_item(tester, bot_username, phrase):
    question = f"e2e вопрос из анкеты {int(time.time())}"
    kind = phrase("topics_kind_question", full=True)
    async with tester.conversation(bot_username) as chat:
        await chat.command("start topic")
        await chat.expect(contains=phrase("topics_form_kind"))
        await chat.click(phrase("topics_form_kind_question", full=True))
        # Тестовый аккаунт админ: у него свой текст вопроса, без минимальной длины.
        await chat.expect_edit(contains=phrase("topics_form_ask_question_admin"), timeout=10)
        await chat.send(question)
        await chat.wait_until(contains=f"{kind} - {question}", timeout=10)
        await chat.click(phrase("de-button-confirm", full=True))
        await chat.wait_until(contains=phrase("topics_admin_added"), timeout=10)

        await _delete(chat, phrase, (kind, question))


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "kind_key"), [("question", "topics_kind_question"), ("topic", "topics_kind_topic")]
)
async def test_command_without_text_opens_the_form_of_its_kind(tester, bot_username, phrase, command, kind_key):
    text = f"e2e пункт по команде {command} {int(time.time())}"
    kind = phrase(kind_key, full=True)
    async with tester.conversation(bot_username) as chat:
        await chat.command(command)
        await chat.expect(contains=phrase(f"topics_form_ask_{command}_admin"))
        await chat.send(text)
        await chat.wait_until(contains=f"{kind} - {text}", timeout=10)
        await chat.click(phrase("de-button-confirm", full=True))
        await chat.wait_until(contains=phrase("topics_admin_added"), timeout=10)

        await _delete(chat, phrase, (kind, text))


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_deleted_items_can_be_restored(tester, bot_username, phrase):
    stamp = int(time.time())
    kind = phrase("topics_kind_topic", full=True)
    first, second = f"e2e удалить и вернуть раз {stamp}", f"e2e удалить и вернуть два {stamp}"
    async with tester.conversation(bot_username) as chat:
        for text in (first, second):
            await chat.command(f"topic {text}")
            await chat.expect(contains=text, timeout=15)

        report = await _delete(chat, phrase, (kind, first), (kind, second))
        await report.click(text=phrase("topics_undo", full=True))
        # Отчёт об удалении меняется на «Вернул в список», следом приходит свежий список.
        restored = await chat.expect(contains=first, timeout=15)
        assert second in restored.message
        await chat.wait_until(message=report, contains=phrase("topics_restored"), timeout=10)

        # Номера неизвестного пункта бот не удаляет и ничего не трогает.
        listing, _last = await _show_list(chat, phrase)
        await chat.send("удали 9999")
        await chat.expect(contains=phrase("topics_numbers_unknown"), timeout=15)

        numbers = [_number(listing, kind, text) for text in (first, second)]
        await chat.command("done " + " ".join(map(str, numbers)))
        await chat.expect(contains=phrase("topics_removed"), timeout=15)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_buttons_under_the_list_delete_ticked_items(tester, bot_username, phrase):
    text = f"e2e удалить кнопками {int(time.time())}"
    kind = phrase("topics_kind_topic", full=True)
    async with tester.conversation(bot_username) as chat:
        await chat.command(f"topic {text}")
        await chat.expect(contains=text, timeout=15)

        listing, last = await _show_list(chat, phrase)
        number = _number(listing, kind, text)
        await last.click(text=str(number))
        # Отметка видна и на кнопке, и в тексте списка: значок перед номером,
        # сам пункт зачёркнут, а кнопка удаления показывает, сколько отмечено.
        ticked = await chat.wait_until(message=last, buttons=[f"{MARK}{number}"], timeout=10)
        assert f"{MARK}{number}) {kind} - {text}" in ticked.message
        struck = [entity for entity in ticked.entities or [] if isinstance(entity, types.MessageEntityStrike)]
        assert len(struck) == 1
        remove = MARK + phrase("topics_remove_marked", full=True).replace("{ $count }", "1")
        await ticked.click(text=remove)
        report = await chat.expect(contains=phrase("topics_removed"), timeout=15)
        assert text in report.message
        rest = await chat.get_reply(timeout=15)
        assert text not in rest.message


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.parametrize(("hashtag", "kind_key"), [("тема", "topics_kind_topic"), ("вопрос", "topics_kind_question")])
async def test_hashtag_in_group_lands_on_the_list_with_its_kind(tester, bot_username, phrase, hashtag, kind_key):
    group = _topics_chat()
    text = f"e2e из чата по хештегу {hashtag} {int(time.time())}"
    kind = phrase(kind_key, full=True)
    client = tester.client

    async with _EphemeralInbox(client) as inbox:
        sent = await client.send_message(group, f"#{hashtag} {text}")
        # Автору бот пишет эфемерно, что добавил пункт, и ставит реакцию на сообщение.
        await inbox.next(phrase("topics_added_question" if hashtag == "вопрос" else "topics_added_topic"))
    marked = await client.get_messages(group, ids=sent.id)
    assert marked.reactions is not None and marked.reactions.results

    async with tester.conversation(bot_username) as chat:
        await _delete(chat, phrase, (kind, text))


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ephemeral_form_in_group_adds_the_item(tester, bot_username, phrase):
    group = _topics_chat()
    text = f"e2e эфемерная тема {int(time.time())}"
    kind = phrase("topics_kind_topic", full=True)
    client = tester.client
    bot = await client.get_input_entity(bot_username)
    peer = await client.get_input_entity(group)

    async with _EphemeralInbox(client) as inbox:
        await client(functions.ephemeral.SendMessageRequest(receiver_id=bot, peer=peer, message="/topic"))
        form = await inbox.next(phrase("topics_form_kind"))
        pick = _button_data(form, phrase("topics_form_kind_topic", full=True))
        await client(functions.ephemeral.GetCallbackAnswerRequest(peer=peer, id=form.id, data=pick))
        await inbox.next(phrase("topics_form_ask_topic"))
        await client(
            functions.ephemeral.SendMessageRequest(
                receiver_id=bot, peer=peer, message=text, reply_to=types.InputReplyToEphemeralMessage(id=form.id)
            )
        )
        confirm = await inbox.next(text)
        send = _button_data(confirm, phrase("de-button-confirm", full=True))
        await client(functions.ephemeral.GetCallbackAnswerRequest(peer=peer, id=confirm.id, data=send))
        await inbox.next(phrase("topics_added_topic"))

    async with tester.conversation(bot_username) as chat:
        await _delete(chat, phrase, (kind, text))


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_admin_adds_a_chat_message_by_replying_with_a_command(tester, bot_username, phrase):
    group = _topics_chat()
    text = f"e2e реплика из чата без хештега {int(time.time())}"
    kind = phrase("topics_kind_question", full=True)
    client = tester.client

    said = await client.send_message(group, text)
    async with _EphemeralInbox(client) as inbox:
        await client.send_message(group, "/вопрос", reply_to=said.id)
        added = await inbox.next(phrase("topics_admin_added"))
        assert f"{kind} - {text}" in added.message
    marked = await client.get_messages(group, ids=said.id)
    assert marked.reactions is not None and marked.reactions.results

    async with tester.conversation(bot_username) as chat:
        await _delete(chat, phrase, (kind, text))
