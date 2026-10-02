"""Заметки ведущих и вопросы слушателей: хештеги, хранилище, хендлеры, меню."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.filters import CommandObject
from sagenza_tgbot_sdk.menus.callback import Action, MenuCallback
from sagenza_tgbot_sdk.menus.routing import MenuRouter

from handlers import collector_handler as col
from handlers import menus
from services.collector import Entry, EntryStore, extract_hashtags, pick_tag, strip_hashtags
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


def _pressed(callback: MenuCallback):
    """Контекст нажатия таким, каким его собирает роутер меню SDK."""
    event = MagicMock()
    event.from_user.username = "admin"
    event.from_user.language_code = "ru"
    ctx = menus.menus.context(event, locale="ru", menu_id=callback.m, page=callback.p)
    ctx.put = AsyncMock()
    ctx.answer = AsyncMock()
    return ctx


def _targets(markup) -> set[str]:
    return {MenuCallback.unpack(b.callback_data).m for row in markup.inline_keyboard for b in row}


@pytest.mark.asyncio
async def test_entry_list_buttons_are_routed_though_the_list_has_no_button_of_its_own(fake_redis):
    """Список заметок открывает хендлер группы. Роутер SDK при этом обязан
    пропускать нажатия внутри списка: запись, страницы, «Назад» из карточки."""
    saved = await col.NOTES.store.add(Entry(tag="тема", text="про гостя", author="@admin"))
    router = MenuRouter(menus.menus)
    entries, groups = col.NOTES.entries_menu, col.NOTES.groups_menu

    select = MenuCallback(m=entries, a=Action.SELECT, v=str(saved.id))
    ctx = _pressed(select)
    assert await router.dispatch(ctx, select)
    assert "про гостя" in ctx.put.await_args.args[0]

    page = MenuCallback(m=entries, a=Action.OPEN)
    ctx = _pressed(page)
    assert await router.dispatch(ctx, page)
    assert _targets(ctx.put.await_args.args[1]) == {entries, groups}

    opened = MenuCallback(m=groups, a=Action.OPEN)
    ctx = _pressed(opened)
    assert await router.dispatch(ctx, opened)
    assert entries not in _targets(ctx.put.await_args.args[1])


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
    saved = await col.NOTES.store.add(Entry(tag="тема", text="q", author="x"))
    callback = MagicMock()
    callback.from_user.language_code = "ru"
    data = col.EntryCallback(c="notes", a=action, id=saved.id, p=0)
    ctx = MagicMock(locale="ru", text=lambda key: t(key), answer=AsyncMock(), show=AsyncMock())

    with patch.object(menus.menus, "context", return_value=ctx):
        await col.entry_action(callback, data, state=MagicMock())

    assert await col.NOTES.store.count("тема") == 0
    ctx.answer.assert_awaited_once_with(t(reply))
    ctx.show.assert_awaited_once_with(col.NOTES.entries_menu, 0)
