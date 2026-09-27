"""Заметки ведущих и вопросы слушателей: хештеги, хранилище, хендлеры, меню."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.filters import CommandObject

from handlers import collector_handler as col
from handlers import menus
from services.collector import Entry, EntryStore, extract_hashtags, message_link, pick_tag, strip_hashtags
from services.i18n import t


@pytest.fixture(autouse=True)
def _admins():
    with patch("filters.dispatcher_filters.ADMINS", ["admin"]):
        yield


def test_hashtags_are_lowercased_unique_and_drop_bot_suffix():
    assert extract_hashtags("#Вопрос про #тема и #вопрос@podbot, a#b ##x") == ["вопрос", "тема"]


def test_pick_tag_takes_first_allowed():
    assert pick_tag("#мем #Тема #вопрос", ["вопрос", "тема"]) == "тема"
    assert pick_tag("без тегов", ["вопрос"]) is None


def test_strip_hashtags_keeps_foreign_tags():
    assert strip_hashtags("#вопрос как дела  #мем", ["вопрос"]) == "как дела #мем"


@pytest.mark.parametrize(
    ("username", "chat_id", "link"),
    [
        ("@chat", -1001, "https://t.me/chat/7"),
        (None, -1001234, "https://t.me/c/1234/7"),
        (None, 42, None),
    ],
)
def test_message_link(username, chat_id, link):
    assert message_link(username, chat_id, 7) == link


@pytest.mark.asyncio
async def test_store_groups_marks_used_and_deletes(fake_redis):
    store = EntryStore(fake_redis, "t")
    first = await store.add(Entry(tag="тема", text="a", author="x", created_at=1))
    second = await store.add(Entry(tag="тема", text="b", author="x", created_at=2))
    await store.add(Entry(tag="вопрос", text="c", author="x"))

    assert [e.text for e in await store.list("тема")] == ["b", "a"]
    assert await store.count("вопрос") == 1

    used = await store.mark_used(first.id)
    assert used.used and (await store.get(first.id)).used
    assert [e.id for e in await store.list("тема")] == [second.id]

    assert await store.delete(second.id)
    assert await store.get(second.id) is None
    assert not await store.delete(second.id)
    assert await store.mark_used(999) is None


@pytest.mark.asyncio
async def test_store_skips_already_collected_message(fake_redis):
    store = EntryStore(fake_redis, "t")
    assert await store.add(Entry(tag="вопрос", text="a", author="x"), source=(1, 2))
    assert await store.add(Entry(tag="вопрос", text="a", author="x"), source=(1, 2)) is None
    assert await store.count("вопрос") == 1


def _private_msg(username="admin"):
    msg = MagicMock()
    msg.from_user.username = username
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_note_command_saves_to_hashtag_group(fake_redis):
    msg = _private_msg()
    await col.add_note(msg, CommandObject(command="note", args="#Тема обсудить новости"), language="ru")

    [entry] = await col.NOTES.store.list("тема")
    assert (entry.text, entry.author) == ("обсудить новости", "@admin")
    msg.answer.assert_awaited_once_with(t("collector_saved", tag="тема"))


@pytest.mark.asyncio
async def test_note_without_hashtag_goes_to_default_group(fake_redis):
    await col.add_note(_private_msg(), CommandObject(command="note", args="просто мысль"), language="ru")

    assert await col.NOTES.store.count(col.NOTES.default_tag) == 1


@pytest.mark.asyncio
async def test_empty_command_shows_usage(fake_redis):
    msg = _private_msg("listener")
    await col.add_question(msg, CommandObject(command="ask", args=None), language="ru")

    msg.answer.assert_awaited_once()
    assert "/ask" in msg.answer.await_args.args[0]


def _chat_msg(text, username="test_group", message_id=10):
    msg = MagicMock(text=text, caption=None, message_id=message_id)
    msg.chat.username = username
    msg.chat.id = -100555
    msg.from_user.username = "listener"
    return msg


@pytest.mark.asyncio
async def test_chat_messages_with_listener_hashtags_are_collected(fake_redis):
    await col.collect_from_chat(_chat_msg("#вопрос когда выпуск?"))
    await col.collect_from_chat(_chat_msg("#вопрос когда выпуск?"))
    await col.collect_from_chat(_chat_msg("просто болтовня", message_id=11))

    [entry] = await col.QUESTIONS.store.list("вопрос")
    assert entry.text == "когда выпуск?"
    assert entry.link == "https://t.me/test_group/10"


def test_only_the_podcast_chat_is_read():
    assert col.from_listener_chat(_chat_msg("x", username="Test_Group"))
    assert not col.from_listener_chat(_chat_msg("x", username="other"))
    assert not col.from_listener_chat(_chat_msg("x", username=None))


def _menu_ctx(value=None, state=None):
    event = MagicMock()
    event.from_user.username = "admin"
    event.from_user.language_code = "ru"
    ctx = menus.menus.context(event, {"state": state} if state else {}, locale="ru")
    ctx.value = value
    return ctx


@pytest.mark.asyncio
async def test_groups_menu_shows_counts_and_entry_card(fake_redis):
    saved = await col.NOTES.store.add(Entry(tag="вопрос", text="про гостя", author="@admin"))
    groups = menus.menus.get_menu(col.NOTES.groups_menu)
    items = await groups.source(_menu_ctx())
    assert [i.text for i in items] == ["#тема (0)", "#вопрос (1)", "#комментарий (0)"]

    ctx = _menu_ctx(value=str(saved.id))
    ctx.put = AsyncMock()
    ctx.answer = AsyncMock()
    entries = menus.menus.get_menu(col.NOTES.entries_menu)
    await entries.on_select(ctx)

    text, markup = ctx.put.await_args.args
    assert "про гостя" in text
    assert len(markup.inline_keyboard) == 2


@pytest.mark.asyncio
async def test_open_group_remembers_tag_for_entries_list(fake_redis):
    await col.NOTES.store.add(Entry(tag="вопрос", text="про гостя", author="@admin"))
    data: dict = {}
    state = MagicMock(spec=col.FSMContext)
    state.update_data = AsyncMock(side_effect=lambda d: data.update(d))
    state.get_data = AsyncMock(side_effect=lambda: data)
    ctx = _menu_ctx(value="1", state=state)
    ctx.show = AsyncMock()

    await menus.menus.get_menu(col.NOTES.groups_menu).on_select(ctx)
    items = await menus.menus.get_menu(col.NOTES.entries_menu).source(ctx)

    ctx.show.assert_awaited_once_with(col.NOTES.entries_menu)
    assert [i.text.split(" ", 1)[1] for i in items] == ["про гостя"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "reply"), [("used", "collector_marked_used"), ("del", "collector_deleted")])
async def test_entry_buttons_update_store_and_return_to_list(fake_redis, action, reply):
    saved = await col.QUESTIONS.store.add(Entry(tag="вопрос", text="q", author="x"))
    callback = MagicMock()
    callback.from_user.language_code = "ru"
    data = col.EntryCallback(c="questions", a=action, id=saved.id, p=0)
    ctx = MagicMock(locale="ru", text=lambda key: t(key), answer=AsyncMock(), show=AsyncMock())

    with patch.object(menus.menus, "context", return_value=ctx):
        await col.entry_action(callback, data, state=MagicMock())

    assert await col.QUESTIONS.store.count("вопрос") == 0
    ctx.answer.assert_awaited_once_with(t(reply))
    ctx.show.assert_awaited_once_with(col.QUESTIONS.entries_menu, 0)
