"""Список для ведущих: показ, «удали 1, 3», кнопки, «Вернуть», авторы и бан, раздел /admin."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiogram.enums import ChatType
from aiogram.filters import CommandObject
from aiogram.types import CallbackQuery, Chat, InlineKeyboardMarkup, Message, User
from sagenza_tgbot_sdk.menus.testing import crawl

import config
from forms import topic_suggestion as form
from handlers import menus
from handlers import topics_list_handler as lh
from handlers.topics_list_handler import ListCallback
from services.i18n import t
from services.metrics import bot_metrics
from services.topics import Kind, listing
from services.topics.runtime import topic_list, view_store

ADMIN_ID = 1
HOSTS_ID = -1009999999999


def _user(username="admin", user_id=ADMIN_ID):
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.language_code = "ru"
    return user


def _message(bot, text="", *, chat_id=ADMIN_ID, chat_type=ChatType.PRIVATE, username="admin", markup=None):
    msg = MagicMock(spec=Message)
    msg.bot = bot
    msg.text = text
    msg.from_user = _user(username)
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    msg.chat.type = chat_type
    msg.chat.username = None
    msg.reply_markup = markup
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    msg.edit_reply_markup = AsyncMock()
    return msg


def _press(bot, data: ListCallback | str, message, username="admin"):
    callback = MagicMock(spec=CallbackQuery)
    callback.bot = bot
    callback.data = data.pack() if isinstance(data, ListCallback) else data
    callback.from_user = _user(username)
    callback.message = message
    callback.answer = AsyncMock()
    return callback


async def _click(bot, data: ListCallback, message, state=None, metrics=None, username="admin"):
    callback = _press(bot, data, message, username)
    await lh.on_list_button(callback, data, state or MagicMock(), bot, metrics)
    return callback


def _sent(bot) -> list[dict]:
    return [call.kwargs for call in bot.send_message.await_args_list]


def _texts(bot) -> list[str]:
    return [kwargs["text"] for kwargs in _sent(bot)]


def _labels(markup: InlineKeyboardMarkup) -> list[list[str]]:
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _data(markup: InlineKeyboardMarkup, label: str) -> ListCallback:
    button = next(b for row in markup.inline_keyboard for b in row if b.text == label)
    return ListCallback.unpack(button.callback_data)


async def _ids() -> list[int]:
    return [item.id for item in await topic_list().repository.items()]


@pytest_asyncio.fixture
async def three(fake_redis, add_item):
    """Список из примера ведущих: два вопроса и тема."""
    return [
        await add_item("Почему небо голубое?", Kind.QUESTION),
        await add_item("Почему птицы летают?", Kind.QUESTION, user_id=8, name="@second"),
        await add_item("Как съездили в отпуск"),
    ]


# --- показ ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_command_shows_the_list_with_buttons(three, bot):
    await lh.show_list(_message(bot, "/topics"), bot)

    [shown] = _sent(bot)
    assert shown["text"] == (
        "Список тем и вопросов:\n"
        "1) ВОПРОС - Почему небо голубое?\n"
        "2) ВОПРОС - Почему птицы летают?\n"
        "3) ТЕМА - Как съездили в отпуск"
    )
    assert _labels(shown["reply_markup"]) == [
        ["1", "2", "3"],
        [t("topics_remove_marked"), t("topics_refresh")],
        [t("topics_add_topic"), t("topics_add_question")],
        [t("topics_authors")],
    ]
    view = await view_store().last(ADMIN_ID)
    assert view.ids == [item.id for item in three]


@pytest.mark.asyncio
async def test_empty_list_has_a_clear_phrase_and_no_delete_button(fake_redis, bot):
    await lh.show_list(_message(bot, "/список"), bot)

    [shown] = _sent(bot)
    assert shown["text"] == t("topics_list_empty")
    assert _labels(shown["reply_markup"]) == [
        [t("topics_refresh")],
        [t("topics_add_topic"), t("topics_add_question")],
        [t("topics_authors")],
    ]


@pytest.mark.asyncio
async def test_long_list_goes_in_several_messages_with_own_number_buttons(fake_redis, add_item, bot, monkeypatch):
    monkeypatch.setattr(listing, "MAX_PAGE_ITEMS", 2)
    for index in range(5):
        await add_item(f"тема номер {index}")

    await lh.send_list(bot, ADMIN_ID, "ru", private=True)

    first, second, last = _sent(bot)
    assert first["text"].startswith("Список тем и вопросов:\n1) ТЕМА")
    assert second["text"].startswith("3) ТЕМА")
    assert last["text"].startswith("5) ТЕМА")
    assert _labels(first["reply_markup"]) == [["1", "2"]]
    assert _labels(second["reply_markup"]) == [["3", "4"]]
    assert _labels(last["reply_markup"])[:2] == [["5"], [t("topics_remove_marked"), t("topics_refresh")]]


@pytest.mark.asyncio
async def test_number_buttons_wrap_into_rows(fake_redis, add_item, bot):
    for index in range(8):
        await add_item(f"тема номер {index}")

    await lh.send_list(bot, ADMIN_ID, "ru", private=True)

    rows = _labels(_sent(bot)[0]["reply_markup"])
    assert rows[:2] == [["1", "2", "3", "4", "5", "6"], ["7", "8"]]


@pytest.mark.asyncio
async def test_list_size_is_reported_to_metrics(three, bot):
    await lh.send_list(bot, ADMIN_ID, "ru", private=True)

    rendered = bot_metrics.sdk.render().decode()
    assert 'podboxbot_topics_list_size{bot="podboxbot",kind="question"} 2.0' in rendered
    assert 'podboxbot_topics_list_size{bot="podboxbot",kind="topic"} 1.0' in rendered


# --- удаление текстом и командой ------------------------------------------------


@pytest.mark.asyncio
async def test_delete_by_text_removes_items_and_shows_the_rest(three, bot):
    await lh.show_list(_message(bot, "/topics"), bot)
    bot.send_message.reset_mock()
    metrics = MagicMock()

    await lh.remove_text(_message(bot, "удали 1, 3"), [1, 3], bot, metrics)

    removed, rest = _sent(bot)
    assert removed["text"] == (
        f"{t('topics_removed')}\n1) ВОПРОС - Почему небо голубое?\n3) ТЕМА - Как съездили в отпуск"
    )
    assert _labels(removed["reply_markup"]) == [[t("topics_undo")]]
    assert rest["text"] == "Список тем и вопросов:\n1) ВОПРОС - Почему птицы летают?"
    assert await _ids() == [three[1].id]
    assert [call.kwargs for call in metrics.event.call_args_list] == [{"kind": "question"}, {"kind": "topic"}]
    assert all(call.args == ("topic_removed",) for call in metrics.event.call_args_list)


@pytest.mark.asyncio
async def test_numbers_belong_to_the_list_shown_last(three, add_item, bot):
    await lh.show_list(_message(bot, "/topics"), bot)
    # Пока ведущий читал, слушатели добавили пункты, а первый кто-то удалил.
    await topic_list().remove([three[0].id])
    late = await add_item("поздний вопрос", Kind.QUESTION)
    bot.send_message.reset_mock()

    await lh.remove_text(_message(bot, "удали 2"), [2], bot)

    assert await _ids() == [three[2].id, late.id]
    assert "2) ВОПРОС - Почему птицы летают?" in _texts(bot)[0]


@pytest.mark.asyncio
async def test_each_chat_has_its_own_last_list(three, add_item, bot):
    await lh.show_list(_message(bot, "/topics"), bot)
    await topic_list().remove([three[0].id])
    # Другой админ смотрит список позже и видит другие номера.
    await lh.show_list(_message(bot, "/topics", chat_id=2), bot)

    await lh.remove_text(_message(bot, "удали 1", chat_id=2), [1], bot)

    assert await _ids() == [three[2].id]


@pytest.mark.asyncio
async def test_unknown_numbers_delete_nothing(three, bot):
    await lh.show_list(_message(bot, "/topics"), bot)
    bot.send_message.reset_mock()

    await lh.remove_text(_message(bot, "удали 1, 7, 9"), [1, 7, 9], bot)

    assert _texts(bot) == [t("topics_numbers_unknown", numbers="7, 9", total=3)]
    assert len(await _ids()) == 3


@pytest.mark.asyncio
async def test_without_a_shown_list_nothing_is_deleted(three, bot):
    await lh.remove_text(_message(bot, "удали 1"), [1], bot)

    texts = _texts(bot)
    assert texts[0] == t("topics_view_missing")
    assert texts[1].startswith("Список тем и вопросов:")
    assert len(await _ids()) == 3


@pytest.mark.asyncio
async def test_items_deleted_by_someone_else_are_reported(three, bot):
    await lh.show_list(_message(bot, "/topics"), bot)
    await topic_list().remove([three[0].id])
    bot.send_message.reset_mock()

    await lh.remove_text(_message(bot, "удали 1, 2"), [1, 2], bot)

    removed = _texts(bot)[0]
    assert "2) ВОПРОС - Почему птицы летают?" in removed
    assert "1) ВОПРОС" not in removed
    assert removed.endswith(t("topics_removed_gone", numbers="1"))


@pytest.mark.asyncio
async def test_all_items_already_gone(three, bot):
    await lh.show_list(_message(bot, "/topics"), bot)
    await topic_list().remove([three[0].id])
    bot.send_message.reset_mock()

    await lh.remove_text(_message(bot, "удали 1"), [1], bot)

    first, rest = _sent(bot)
    assert first["text"] == t("topics_removed_nothing", numbers="1")
    assert first.get("reply_markup") is None
    assert rest["text"].startswith("Список тем и вопросов:")


@pytest.mark.asyncio
async def test_done_command_deletes_like_the_text(three, bot):
    await lh.show_list(_message(bot, "/topics"), bot)

    await lh.remove_command(_message(bot, "/done 1 3"), CommandObject(command="done", args="1 3"), bot)

    assert await _ids() == [three[1].id]


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [None, "все", "1 и ещё вот этот"])
async def test_done_command_without_numbers_explains_itself(three, bot, args):
    msg = _message(bot, "/done")

    await lh.remove_command(msg, CommandObject(command="done", args=args), bot)

    msg.answer.assert_awaited_once_with(t("topics_remove_usage"))
    assert len(await _ids()) == 3


@pytest.mark.asyncio
async def test_long_removal_report_is_cut(fake_redis, add_item, bot, monkeypatch):
    for index in range(6):
        await add_item(f"тема номер {index} про что-нибудь важное")
    await lh.send_list(bot, ADMIN_ID, "ru", private=True)
    monkeypatch.setattr(lh, "MAX_PAGE_CHARS", 120)
    bot.send_message.reset_mock()

    await lh.remove_numbers(bot, ADMIN_ID, ADMIN_ID, [1, 2, 3, 4, 5, 6], "ru", private=True, metrics=None)

    report = _texts(bot)[0]
    assert report.splitlines()[-1] == t("topics_removed_more", count=4)
    assert await _ids() == []


# --- кнопки ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marking_and_deleting_with_buttons(three, bot):
    await lh.show_list(_message(bot, "/topics"), bot)
    markup = _sent(bot)[0]["reply_markup"]
    under_list = _message(bot, markup=markup)

    first = await _click(bot, _data(markup, "1"), under_list)
    marked = under_list.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert _labels(marked)[0] == ["✅ 1", "2", "3"]
    first.answer.assert_awaited_once_with(t("topics_marked", numbers="1"))

    under_list.reply_markup = marked
    await _click(bot, _data(marked, "3"), under_list)
    marked = under_list.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert _labels(marked)[0] == ["✅ 1", "2", "✅ 3"]

    # Снять отметку можно той же кнопкой.
    under_list.reply_markup = marked
    unmark = await _click(bot, _data(marked, "✅ 3"), under_list)
    marked = under_list.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert _labels(marked)[0] == ["✅ 1", "2", "3"]
    unmark.answer.assert_awaited_once_with(t("topics_marked", numbers="1"))

    bot.send_message.reset_mock()
    await _click(bot, _data(marked, t("topics_remove_marked")), under_list)

    assert await _ids() == [three[1].id, three[2].id]
    assert "1) ВОПРОС - Почему небо голубое?" in _texts(bot)[0]


@pytest.mark.asyncio
async def test_delete_button_needs_marks(three, bot):
    await lh.show_list(_message(bot, "/topics"), bot)
    markup = _sent(bot)[0]["reply_markup"]

    press = await _click(bot, _data(markup, t("topics_remove_marked")), _message(bot, markup=markup))

    press.answer.assert_awaited_once_with(t("topics_mark_first"), show_alert=True)
    assert len(await _ids()) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["2", "🗑 Удалить отмеченные"])
async def test_buttons_of_an_old_list_say_it_is_stale(three, bot, label):
    await lh.show_list(_message(bot, "/topics"), bot)
    old = _sent(bot)[0]["reply_markup"]
    await lh.show_list(_message(bot, "/topics"), bot)
    bot.send_message.reset_mock()
    under_old = _message(bot, markup=old)

    press = await _click(bot, _data(old, label), under_old)

    press.answer.assert_awaited_once_with(t("topics_list_stale"), show_alert=True)
    under_old.edit_reply_markup.assert_not_awaited()
    assert _texts(bot)[0].startswith("Список тем и вопросов:")
    assert len(await _ids()) == 3


@pytest.mark.asyncio
async def test_refresh_sends_a_fresh_list(three, add_item, bot):
    await lh.show_list(_message(bot, "/topics"), bot)
    markup = _sent(bot)[0]["reply_markup"]
    await add_item("свежая тема про погоду")
    bot.send_message.reset_mock()

    await _click(bot, _data(markup, t("topics_refresh")), _message(bot, markup=markup))

    assert "4) ТЕМА - свежая тема про погоду" in _texts(bot)[0]


# --- вернуть --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_brings_items_back_once(three, bot):
    await lh.show_list(_message(bot, "/topics"), bot)
    bot.send_message.reset_mock()
    await lh.remove_text(_message(bot, "удали 1, 3"), [1, 3], bot)
    report = _sent(bot)[0]
    under_report = _message(bot, markup=report["reply_markup"])
    bot.send_message.reset_mock()
    metrics = MagicMock()

    await _click(bot, _data(report["reply_markup"], t("topics_undo")), under_report, metrics=metrics)

    assert await _ids() == [item.id for item in three]
    back = under_report.edit_text.await_args.args[0]
    assert back == f"{t('topics_restored')}\n1) ВОПРОС - Почему небо голубое?\n3) ТЕМА - Как съездили в отпуск"
    assert _texts(bot)[0].count("\n") == 3
    assert metrics.event.call_count == 2
    metrics.event.assert_any_call("topic_restored", kind="topic")

    again = await _click(bot, _data(report["reply_markup"], t("topics_undo")), under_report)
    again.answer.assert_awaited_once_with(t("topics_undo_expired"), show_alert=True)
    under_report.edit_reply_markup.assert_awaited_once_with(reply_markup=None)


@pytest.mark.asyncio
async def test_undo_expires(three, bot, fake_redis):
    await lh.show_list(_message(bot, "/topics"), bot)
    bot.send_message.reset_mock()
    await lh.remove_text(_message(bot, "удали 2"), [2], bot)
    report = _sent(bot)[0]
    for key in await fake_redis.keys("topics:undo:*"):
        assert 0 < await fake_redis.ttl(key) <= 600
        await fake_redis.delete(key)

    press = await _click(bot, _data(report["reply_markup"], t("topics_undo")), _message(bot))

    press.answer.assert_awaited_once_with(t("topics_undo_expired"), show_alert=True)
    assert len(await _ids()) == 2


# --- добавление админом -----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "ask"), [("➕ Тема", "topics_form_ask_topic"), ("➕ Вопрос", "topics_form_ask_question")]
)
async def test_add_buttons_open_the_admin_form(three, bot, label, ask):
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage

    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=ADMIN_ID, user_id=ADMIN_ID))
    await lh.show_list(_message(bot, "/topics"), bot)
    markup = _sent(bot)[0]["reply_markup"]
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=11))

    await _click(bot, _data(markup, label), _message(bot, markup=markup), state=state)

    assert bot.send_message.await_args.kwargs["text"] == t(ask, min=1, max=50)
    session, _ui = await form.TYPED.storage.load(state)
    assert session.context["trusted"] is True


# --- авторы и бан -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_authors_can_be_banned_and_unbanned_from_the_list(three, bot):
    await lh.show_list(_message(bot, "/topics"), bot)
    markup = _sent(bot)[0]["reply_markup"]
    under_list = _message(bot, markup=markup)

    await _click(bot, _data(markup, t("topics_authors")), under_list)
    text, authors = under_list.answer.await_args.args[0], under_list.answer.await_args.kwargs["reply_markup"]
    assert text == t("topics_authors_title")
    assert _labels(authors) == [
        [t("topics_author", name="@listener", count=2)],
        [t("topics_author", name="@second", count=1)],
    ]

    panel = _message(bot, markup=authors)
    metrics = MagicMock()
    ban = await _click(bot, _data(authors, t("topics_author", name="@second", count=1)), panel, metrics=metrics)
    ban.answer.assert_awaited_once_with(t("topics_ban_done"))
    assert await topic_list().repository.banned() == {8: "@second"}
    metrics.event.assert_called_once_with("topic_author", action="ban")
    after_ban = panel.edit_text.await_args.kwargs["reply_markup"]
    assert _labels(after_ban) == [
        [t("topics_author_banned", name="@second")],
        [t("topics_author", name="@listener", count=2)],
    ]

    unban = await _click(bot, _data(after_ban, t("topics_author_banned", name="@second")), panel)
    unban.answer.assert_awaited_once_with(t("topics_unban_done"))
    assert await topic_list().repository.banned() == {}


@pytest.mark.asyncio
async def test_banned_author_stays_visible_without_items(fake_redis, bot):
    await topic_list().repository.ban(8, "@second")

    text, markup = await lh.authors_view("ru")

    assert text == t("topics_authors_title")
    assert _labels(markup) == [[t("topics_author_banned", name="@second")]]


@pytest.mark.asyncio
async def test_nobody_to_ban(fake_redis, add_item, bot):
    await add_item("от имени канала", user_id=None, name="Podcast channel")

    assert await lh.authors_view("ru") == (t("topics_authors_empty"), None)


# --- кто и где -------------------------------------------------------------------


def test_list_is_for_admins_in_private_by_default(bot):
    assert lh._hosts_place(_message(bot))
    assert not lh._hosts_place(_message(bot, username="listener"))
    assert not lh._hosts_place(_message(bot, chat_id=HOSTS_ID, chat_type=ChatType.SUPERGROUP))


def test_hosts_chat_is_opt_in(bot, monkeypatch):
    monkeypatch.setattr(config, "TOPICS_HOSTS_CHAT", str(HOSTS_ID))
    in_hosts_chat = _message(bot, chat_id=HOSTS_ID, chat_type=ChatType.SUPERGROUP)

    assert lh._hosts_place(in_hosts_chat)
    assert lh._hosts_place(_press(bot, ListCallback(a=lh.REFRESH), in_hosts_chat))
    assert not lh._hosts_place(_message(bot, chat_id=HOSTS_ID, chat_type=ChatType.SUPERGROUP, username="listener"))
    assert not lh._hosts_place(_message(bot, chat_id=-5, chat_type=ChatType.SUPERGROUP))


@pytest.mark.asyncio
async def test_hosts_chat_gets_the_list_without_private_only_buttons(three, bot, monkeypatch):
    monkeypatch.setattr(config, "TOPICS_HOSTS_CHAT", str(HOSTS_ID))
    in_hosts_chat = _message(bot, "/topics", chat_id=HOSTS_ID, chat_type=ChatType.SUPERGROUP)

    await lh.show_list(in_hosts_chat, bot)

    [shown] = _sent(bot)
    assert shown["chat_id"] == HOSTS_ID
    assert _labels(shown["reply_markup"]) == [["1", "2", "3"], [t("topics_remove_marked"), t("topics_refresh")]]

    # Старая кнопка «➕» из лички в чате ведущих ничего не открывает.
    press = await _click(bot, ListCallback(a=lh.ADD_TOPIC), in_hosts_chat)
    press.answer.assert_awaited_once_with()
    assert len(_sent(bot)) == 1


@pytest.mark.asyncio
async def test_foreign_press_is_refused(bot):
    press = _press(bot, ListCallback(a=lh.REFRESH), _message(bot), username="listener")

    await lh.on_foreign_button(press)

    press.answer.assert_awaited_once_with(t("topics_denied"), show_alert=True)


def _real_message(text: str, username: str = "admin", chat_type: str = "private") -> Message:
    user = User(id=ADMIN_ID, is_bot=False, first_name="Host", username=username, language_code="ru")
    chat = Chat(id=ADMIN_ID if chat_type == "private" else -5, type=chat_type)
    return Message(message_id=1, date=datetime.now(), chat=chat, from_user=user, text=text)


async def _handled_by(handler, message: Message, bot) -> bool:
    handlers = [h for h in lh.router.message.handlers if h.callback is handler]
    return any([(await h.check(message, bot=bot))[0] for h in handlers])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "handler"),
    [
        ("/topics", lh.show_list),
        ("/список", lh.show_list),
        ("/done 1 3 4", lh.remove_command),
        ("/удали 2", lh.remove_command),
        ("удали 1, 3, 4", lh.remove_text),
        ("Удали пункты 1, 3, 4", lh.remove_text),
    ],
)
async def test_admin_messages_are_routed(bot, text, handler):
    assert await _handled_by(handler, _real_message(text), bot)
    assert not await _handled_by(handler, _real_message(text, username="listener"), bot)
    assert not await _handled_by(handler, _real_message(text, chat_type="supergroup"), bot)


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["удали всё", "Number: 999", "просто текст"])
async def test_other_texts_pass_by(bot, text):
    assert not await _handled_by(lh.remove_text, _real_message(text), bot)


@pytest.mark.asyncio
async def test_nothing_works_when_the_flag_is_off(bot, monkeypatch):
    monkeypatch.setattr(config, "TOPICS_ENABLED", False)

    assert not await _handled_by(lh.show_list, _real_message("/topics"), bot)
    assert not await _handled_by(lh.remove_text, _real_message("удали 1"), bot)


# --- раздел /admin ----------------------------------------------------------------


def _admin_event(username="admin"):
    event = MagicMock()
    event.from_user.username = username
    event.from_user.language_code = "ru"
    return event


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["ru", "en"])
async def test_topics_menu_opens_and_is_wired(three, locale):
    ctx = menus.menus.context(_admin_event(), locale=locale)

    report = await crawl(menus.menus, ctx, locales=[locale])

    report.raise_for_problems()
    assert {f"{lh.TOPICS_MENU}@0"} <= set(report.opened)


@pytest.mark.asyncio
async def test_topics_section_is_hidden_when_the_flag_is_off(fake_redis, monkeypatch):
    ctx = menus.menus.context(_admin_event(), locale="ru")
    _text, markup = await menus.menus.render(ctx, menus.ADMIN_MENU)
    assert t("admin_topics") in [button.text for row in markup.inline_keyboard for button in row]

    monkeypatch.setattr(config, "TOPICS_ENABLED", False)
    _text, markup = await menus.menus.render(ctx, menus.ADMIN_MENU)
    assert t("admin_topics") not in [button.text for row in markup.inline_keyboard for button in row]


@pytest.mark.asyncio
async def test_topics_menu_buttons(three, bot, monkeypatch):
    ctx = menus.menus.context(_admin_event(), locale="ru")
    _text, markup = await menus.menus.render(ctx, lh.TOPICS_MENU)
    assert _labels(markup)[:4] == [
        [t("topics_show")],
        [t("topics_add_topic"), t("topics_add_question")],
        [t("topics_authors")],
        [t("topics_post_button")],
    ]

    monkeypatch.setattr(config, "TOPICS_FORM_MODE", "off")
    _text, markup = await menus.menus.render(ctx, lh.TOPICS_MENU)
    assert [t("topics_post_button")] not in _labels(markup)


@pytest.mark.asyncio
async def test_show_button_of_the_menu_sends_the_list(three, bot):
    message = _message(bot)
    ctx = MagicMock(data={"bot": bot}, message=message, locale="ru", answer=AsyncMock())

    await lh._show_from_menu(ctx)

    assert _texts(bot)[0].startswith("Список тем и вопросов:\n1) ВОПРОС")
    assert (await view_store().last(ADMIN_ID)).ids == [item.id for item in three]
