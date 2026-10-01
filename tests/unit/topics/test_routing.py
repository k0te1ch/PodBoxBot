"""Кому из хендлеров бота достаётся сообщение, если идти по роутерам по порядку.

Отдельные хендлеры проверены в соседних файлах, но ошибку порядка так не
поймать: сообщение может съесть роутер, который стоит раньше. Здесь сообщение
проходит тот же путь, что в диспетчере: роутеры из ``ROUTERS`` по очереди,
сначала фильтры роутера, потом фильтры хендлеров.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User
from dialog_engine.integrations.aiogram import DefaultSender

import config
from forms import topic_suggestion as form
from forms.service_message import service_message_runner
from forms.upload_file import upload_file_runner
from handlers import ROUTERS
from handlers import topics_form_handler as fh
from services.topics import Kind

GROUP_ID = -1001234567890
ADMIN = User(id=1, is_bot=False, first_name="Host", username="admin", language_code="ru")
LISTENER = User(id=7, is_bot=False, first_name="Listener", username="listener", language_code="ru")


def _private(text: str, user: User = ADMIN) -> Message:
    return Message(message_id=1, date=datetime.now(), chat=Chat(id=user.id, type="private"), from_user=user, text=text)


def _group(text: str, user: User = LISTENER, *, reply_to: Message | None = None, ephemeral_id: int | None = None):
    chat = Chat(id=GROUP_ID, type="supergroup", username="test_group")
    return Message(
        message_id=50,
        date=datetime.now(),
        chat=chat,
        from_user=user,
        text=text,
        reply_to_message=reply_to,
        ephemeral_message_id=ephemeral_id,
    )


def _state(message: Message) -> FSMContext:
    key = StorageKey(bot_id=1, chat_id=message.chat.id, user_id=message.from_user.id)
    return FSMContext(storage=MemoryStorage(), key=key)


async def _taken_by(message: Message, state: FSMContext | None = None) -> str | None:
    """Имя хендлера, который возьмёт сообщение, или ``None``."""
    data = {"bot": MagicMock(), "state": state or _state(message)}
    for router in ROUTERS:
        observer = router.message
        passed, _extra = await observer._handler.check(message, **data)
        if not passed:
            continue
        for handler in observer.handlers:
            matched, _extra = await handler.check(message, **data)
            if matched:
                return handler.callback.__name__
    return None


def _sender_bot(chat_id: int) -> MagicMock:
    sent = MagicMock(message_id=11)
    sent.chat.id = chat_id
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=sent)
    return bot


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "handler"),
    [
        ("/topics", "show_list"),
        ("/список", "show_list"),
        ("удали 1, 3", "remove_text"),
        ("/done 1 3", "remove_command"),
        ("/тема Как съездили в отпуск", "private_command"),
        ("/вопрос", "private_command"),
        ("/start topic", "start_in_private"),
        ("/admin", "admin"),
        ("/start", "start"),
        ("/note #тема не забыть про гостей", "add_note"),
    ],
)
async def test_admin_private_messages(fake_redis, text, handler):
    assert await _taken_by(_private(text)) == handler


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "handler"),
    [
        ("/тема Как съездили в отпуск", "private_command"),
        ("/question", "private_command"),
        ("/start topic", "start_in_private"),
        ("/topics", None),
        ("удали 1, 3", None),
        ("/done 1", None),
    ],
)
async def test_listener_private_messages(fake_redis, text, handler):
    assert await _taken_by(_private(text, LISTENER)) == handler


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "handler"),
    [
        (_group("#тема как выбирать гостей"), "collect_from_chat"),
        (_group("Почему небо голубое? #вопрос"), "collect_from_chat"),
        (_group("просто болтаю"), None),
        (_group("/topic"), "group_command"),
        (_group("/вопрос Почему небо голубое?"), "group_command"),
        (_group("/topic #тема про кино"), "group_command"),
        (_group("/тема", reply_to=_group("чужая реплика")), "group_command"),
        (_group("/тема", ADMIN, reply_to=_group("чужая реплика")), "add_by_reply"),
        (_group("/Вопрос", ADMIN, reply_to=_group("чужая реплика")), "add_by_reply"),
        (_group("/topics", ADMIN), None),
        (_group("удали 1, 3", ADMIN), None),
    ],
)
async def test_topics_chat_messages(fake_redis, message, handler):
    assert await _taken_by(message) == handler


@pytest.mark.asyncio
async def test_ephemeral_answer_with_a_hashtag_goes_to_the_form(fake_redis):
    answer = _group("#вопрос почему небо голубое?", ephemeral_id=6)
    state = _state(answer)
    await form.TYPED.group_runner.start(
        state, DefaultSender(_sender_bot(GROUP_ID), GROUP_ID), context={"lang": "ru", form.KIND: Kind.QUESTION.value}
    )

    assert await _taken_by(answer, state) == "text"
    # Без анкеты эфемерное сообщение с хештегом никто не берёт: это не реплика в чате.
    assert await _taken_by(_group("#вопрос почему небо голубое?", ephemeral_id=6)) is None


@pytest.mark.asyncio
async def test_messages_in_other_chats_are_left_alone(fake_redis):
    elsewhere = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=-1009, type="supergroup", username="other"),
        from_user=LISTENER,
        text="#тема не туда",
    )

    assert await _taken_by(elsewhere) is None


@pytest.mark.asyncio
async def test_nothing_is_taken_when_topics_are_off(fake_redis, monkeypatch):
    monkeypatch.setattr(config, "TOPICS_ENABLED", False)

    assert await _taken_by(_group("#тема как выбирать гостей")) is None
    assert await _taken_by(_group("/topic")) is None
    assert await _taken_by(_private("/topics")) is None
    assert await _taken_by(_private("/тема про кино", LISTENER)) is None


@pytest.mark.asyncio
async def test_form_mode_off_closes_the_form_to_listeners_but_not_to_admins(fake_redis, monkeypatch):
    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "off")

    assert await _taken_by(_private("/тема про кино", LISTENER)) is None
    assert await _taken_by(_group("/topic")) is None
    assert await _taken_by(_private("/тема про кино")) == "private_command"

    # Анкета админа (кнопка «➕ Тема») ведётся и при выключенной анкете слушателей.
    answer = _private("Как съездили в отпуск")
    state = _state(answer)
    await fh.start_private_form(_sender_bot(ADMIN.id), state, ADMIN.id, ADMIN, Kind.TOPIC, trusted=True, metrics=None)
    assert await _taken_by(answer, state) == "text"


@pytest.mark.asyncio
async def test_command_is_not_an_answer_to_an_open_form(fake_redis):
    message = _private("/start")
    state = _state(message)
    await fh.start_private_form(_sender_bot(ADMIN.id), state, ADMIN.id, ADMIN, Kind.TOPIC, trusted=True, metrics=None)

    assert await _taken_by(message, state) == "start"
    assert await _taken_by(_private("Как съездили в отпуск"), state) == "text"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runner", "handler"), [(upload_file_runner, "set_template"), (service_message_runner, "on_text")]
)
async def test_text_goes_to_the_dialog_used_last(fake_redis, monkeypatch, runner, handler):
    message = _private("текст для диалога, открытого последним")
    state = _state(message)
    bot = _sender_bot(ADMIN.id)
    typed = form.TYPED.private_runner.engine

    # Анкета открыта раньше, другой диалог позже: текст его.
    monkeypatch.setattr(typed, "_clock", lambda: 1000.0)
    await fh.start_private_form(bot, state, ADMIN.id, ADMIN, Kind.TOPIC, trusted=True, metrics=None)
    monkeypatch.setattr(runner.engine, "_clock", lambda: 2000.0)
    await runner.start(state, DefaultSender(bot, ADMIN.id), context={"lang": "ru"})
    assert await _taken_by(message, state) == handler

    # Анкету открыли заново, уже после него: текст её.
    monkeypatch.setattr(typed, "_clock", lambda: 3000.0)
    await fh.start_private_form(bot, state, ADMIN.id, ADMIN, Kind.TOPIC, trusted=True, metrics=None)
    assert await _taken_by(message, state) == "text"


@pytest.mark.asyncio
async def test_expired_form_gives_way_to_a_live_dialog(fake_redis, monkeypatch):
    message = _private("Сегодня выпуска не будет")
    state = _state(message)
    bot = _sender_bot(ADMIN.id)
    typed = form.TYPED.private_runner.engine
    service = service_message_runner.engine

    monkeypatch.setattr(service, "_clock", lambda: 1000.0)
    await service_message_runner.start(state, DefaultSender(bot, ADMIN.id), context={"lang": "ru"})
    monkeypatch.setattr(typed, "_clock", lambda: 2000.0)
    await fh.start_private_form(bot, state, ADMIN.id, ADMIN, Kind.TOPIC, trusted=True, metrics=None)
    assert await _taken_by(message, state) == "text"

    # Анкета устарела, сервисное сообщение ещё ждёт текст.
    later = 2000.0 + typed.ttl + 1
    monkeypatch.setattr(typed, "_clock", lambda: later)
    monkeypatch.setattr(service, "_clock", lambda: later)
    assert service.ttl > typed.ttl + 1001
    assert await _taken_by(message, state) == "on_text"
