"""Очередь тем в /admin: видимость, статусы, карточка, номер выпуска и бан автора."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sagenza_tgbot_sdk.menus.callback import Action, MenuCallback
from sagenza_tgbot_sdk.menus.routing import MenuRouter
from sagenza_tgbot_sdk.menus.testing import crawl

import config
from handlers import menus
from handlers import topics_handler as th
from services.i18n import t
from services.topics import Author, Topic, TopicSource, TopicStatus
from services.topics.runtime import topic_service


def _admin_event(username="admin"):
    event = MagicMock()
    event.from_user.username = username
    event.from_user.language_code = "ru"
    return event


def _ctx(value=None, state=None, page=0):
    ctx = menus.menus.context(_admin_event(), {"state": state} if state else {}, locale="ru")
    ctx.value = value
    ctx.page = page
    return ctx


def _fsm():
    data: dict = {}
    current: dict = {"state": None}
    state = MagicMock(spec=th.FSMContext)
    state.update_data = AsyncMock(side_effect=lambda d: data.update(d))
    state.get_data = AsyncMock(side_effect=lambda: data)

    async def set_state(value=None):
        current["state"] = getattr(value, "state", value)

    state.set_state = AsyncMock(side_effect=set_state)
    state.get_state = AsyncMock(side_effect=lambda: current["state"])
    return state


async def _add(text="про гостей из Питера", status=TopicStatus.NEW, user_id=7) -> Topic:
    topic = await topic_service().repository.add(
        Topic(text=text, author=Author(name="@listener", user_id=user_id), source=TopicSource.HASHTAG, chat_id=-100)
    )
    if status is not TopicStatus.NEW:
        topic = await topic_service().repository.set_status(topic.id, status)
    return topic


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["ru", "en"])
async def test_topics_menus_open_and_are_wired(fake_redis, locale):
    await _add()
    ctx = menus.menus.context(_admin_event(), locale=locale)

    report = await crawl(menus.menus, ctx, locales=[locale])

    report.raise_for_problems()
    assert {"topics@0"} <= set(report.opened)


@pytest.mark.asyncio
async def test_topics_hidden_when_flag_is_off(fake_redis, monkeypatch):
    monkeypatch.setattr(config, "TOPICS_ENABLED", False)

    _text, markup = await menus.menus.render(_ctx(), menus.ADMIN_MENU)

    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert t("admin_topics") not in labels


@pytest.mark.asyncio
async def test_statuses_show_counts_and_open_their_list(fake_redis):
    await _add("новая тема раз")
    await _add("отложенная тема", status=TopicStatus.LATER)
    state = _fsm()
    ctx = _ctx(value="later", state=state)
    ctx.show = AsyncMock()

    items = await menus.menus.get_menu(th.STATUSES_MENU).source(ctx)
    await menus.menus.get_menu(th.STATUSES_MENU).on_select(ctx)
    entries = await menus.menus.get_menu(th.ENTRIES_MENU).source(ctx)

    assert [i.text for i in items] == [
        f"{t('topics_status_new')} (1)",
        f"{t('topics_status_later')} (1)",
        f"{t('topics_status_taken')} (0)",
        f"{t('topics_status_rejected')} (0)",
    ]
    ctx.show.assert_awaited_once_with(th.ENTRIES_MENU)
    assert [i.text.split(" ", 1)[1] for i in entries] == ["отложенная тема"]


def _pressed(callback: MenuCallback, username="admin"):
    """Контекст нажатия таким, каким его собирает роутер меню SDK."""
    ctx = menus.menus.context(_admin_event(username), locale="ru", menu_id=callback.m, page=callback.p)
    ctx.put = AsyncMock()
    ctx.answer = AsyncMock()
    return ctx


def _targets(markup) -> set[str]:
    return {MenuCallback.unpack(b.callback_data).m for row in markup.inline_keyboard for b in row}


@pytest.mark.asyncio
async def test_list_buttons_are_routed_though_the_list_has_no_button_of_its_own(fake_redis):
    """Список тем открывает хендлер статуса. Роутер SDK при этом обязан
    пропускать нажатия внутри списка: тему, страницы, «Назад» из карточки."""
    topic = await _add("тема про гостей")
    router = MenuRouter(menus.menus)

    select = MenuCallback(m=th.ENTRIES_MENU, a=Action.SELECT, v=str(topic.id))
    ctx = _pressed(select)
    assert await router.dispatch(ctx, select)
    assert "тема про гостей" in ctx.put.await_args.args[0]

    page = MenuCallback(m=th.ENTRIES_MENU, a=Action.OPEN)
    ctx = _pressed(page)
    assert await router.dispatch(ctx, page)
    assert _targets(ctx.put.await_args.args[1]) == {th.ENTRIES_MENU, th.STATUSES_MENU}


@pytest.mark.asyncio
async def test_list_has_no_button_among_statuses_and_stays_admin_only(fake_redis):
    await _add()
    router = MenuRouter(menus.menus)

    statuses = MenuCallback(m=th.STATUSES_MENU, a=Action.OPEN)
    ctx = _pressed(statuses)
    assert await router.dispatch(ctx, statuses)
    assert th.ENTRIES_MENU not in _targets(ctx.put.await_args.args[1])

    select = MenuCallback(m=th.ENTRIES_MENU, a=Action.SELECT, v="1")
    stranger = _pressed(select, username="stranger")
    assert not await router.dispatch(stranger, select)
    stranger.put.assert_not_awaited()


@pytest.mark.asyncio
async def test_card_offers_every_status_but_the_current_one(fake_redis):
    topic = await _add("тема <про> гостей", status=TopicStatus.LATER)
    ctx = _ctx(value=str(topic.id))
    ctx.put = AsyncMock()
    ctx.answer = AsyncMock()

    await menus.menus.get_menu(th.ENTRIES_MENU).on_select(ctx)

    text, markup = ctx.put.await_args.args
    assert "тема &lt;про&gt; гостей" in text
    assert t("topics_status_later") in text
    decisions = [th.TopicCallback.unpack(b.callback_data).a for b in markup.inline_keyboard[0]]
    assert decisions == [th.ASK_EPISODE, "rejected"]
    assert th.TopicCallback.unpack(markup.inline_keyboard[1][0].callback_data).a == th.BAN


@pytest.mark.asyncio
async def test_missing_topic_card_returns_to_list(fake_redis):
    ctx = _ctx(value="42")
    ctx.answer = AsyncMock()
    ctx.show = AsyncMock()

    await menus.menus.get_menu(th.ENTRIES_MENU).on_select(ctx)

    ctx.answer.assert_awaited_once_with(t("topics_missing"), alert=True)
    ctx.show.assert_awaited_once_with(th.ENTRIES_MENU, 0)


def _decide_ctx():
    return MagicMock(
        locale="ru",
        page=0,
        data={},
        text=lambda key, **kw: t(key, **kw),
        answer=AsyncMock(),
        show=AsyncMock(),
        put=AsyncMock(),
    )


def _press(user_id=1):
    callback = MagicMock()
    callback.from_user.id = user_id
    return callback


@pytest.mark.asyncio
async def test_take_without_number_moves_topic_notifies_author_and_counts(fake_redis, bot):
    topic = await _add()
    ctx, metrics = _decide_ctx(), MagicMock()

    with patch.object(menus.menus, "context", return_value=ctx):
        await th.decide(_press(), th.TopicCallback(a="taken", id=topic.id, p=1), _fsm(), bot, metrics)

    stored = await topic_service().repository.get(topic.id)
    assert (stored.status, stored.note) == (TopicStatus.TAKEN, None)
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 7
    assert kwargs["text"] == t("suggest-notify-taken", text="про гостей из Питера")
    metrics.event.assert_called_once_with("suggestion_moderated", status="taken")
    ctx.answer.assert_awaited_once_with(t("topics_marked_taken"))
    ctx.show.assert_awaited_once_with(th.ENTRIES_MENU, 1)


@pytest.mark.asyncio
async def test_take_asks_for_episode_number_first(fake_redis, bot):
    topic = await _add()
    ctx, state = _decide_ctx(), _fsm()

    with patch.object(menus.menus, "context", return_value=ctx):
        await th.decide(_press(), th.TopicCallback(a=th.ASK_EPISODE, id=topic.id, p=2), state, bot)

    assert await state.get_state() == th.TopicStates.episode.state
    assert (await state.get_data())[th.EPISODE_TOPIC_KEY] == topic.id
    text, markup = ctx.put.await_args.args
    assert text == t("topics_ask_episode", id=topic.id, max=th.EPISODE_MAX_CHARS)
    actions = [th.TopicCallback.unpack(row[0].callback_data).a for row in markup.inline_keyboard]
    assert actions == ["taken", th.CARD]
    assert (await topic_service().repository.get(topic.id)).status is TopicStatus.NEW
    bot.send_message.assert_not_awaited()


def _admin_message(text):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = 1
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_episode_number_takes_topic_and_tells_author(fake_redis, bot):
    topic = await _add()
    ctx, state, metrics = _decide_ctx(), _fsm(), MagicMock()
    with patch.object(menus.menus, "context", return_value=ctx):
        await th.decide(_press(), th.TopicCallback(a=th.ASK_EPISODE, id=topic.id, p=2), state, bot)
        msg = _admin_message(" 42 ")
        await th.take_with_episode(msg, state, bot, metrics)

    stored = await topic_service().repository.get(topic.id)
    assert (stored.status, stored.note) == (TopicStatus.TAKEN, "42")
    assert await state.get_state() is None
    notice = bot.send_message.await_args.kwargs
    assert notice["chat_id"] == 7
    assert notice["text"] == t("suggest-notify-taken-note", text="про гостей из Питера", note="42")
    msg.answer.assert_awaited_once_with(t("topics_marked_taken_episode", note="42"))
    card, _markup = ctx.put.await_args.args
    assert t("topics_card_episode", note="42") in card
    assert ctx.page == 2
    metrics.event.assert_called_once_with("suggestion_moderated", status="taken")


@pytest.mark.asyncio
async def test_only_fresh_short_text_counts_as_episode_number(fake_redis):
    state = _fsm()
    await state.update_data({th.EPISODE_ASKED_KEY: th.time.time()})

    assert await th._is_episode_answer(_admin_message("42"), state)
    assert not await th._is_episode_answer(_admin_message("x" * (th.EPISODE_MAX_CHARS + 1)), state)

    await state.update_data({th.EPISODE_ASKED_KEY: th.time.time() - th.EPISODE_WAIT_SECONDS - 1})
    assert not await th._is_episode_answer(_admin_message("42"), state)


@pytest.mark.asyncio
async def test_back_from_episode_question_returns_to_card(fake_redis, bot):
    topic = await _add()
    ctx, state = _decide_ctx(), _fsm()
    await state.set_state(th.TopicStates.episode)

    with patch.object(menus.menus, "context", return_value=ctx):
        await th.decide(_press(), th.TopicCallback(a=th.CARD, id=topic.id), state, bot)

    assert await state.get_state() is None
    text, _markup = ctx.put.await_args.args
    assert t("topics_card_title", id=topic.id) in text


@pytest.mark.asyncio
async def test_ban_and_unban_author_from_card(fake_redis, bot):
    topic = await _add()
    ctx = _decide_ctx()

    with patch.object(menus.menus, "context", return_value=ctx):
        await th.decide(_press(), th.TopicCallback(a=th.BAN, id=topic.id), _fsm(), bot)
        assert await topic_service().repository.is_banned(7)
        text, markup = ctx.put.await_args.args
        assert t("topics_card_banned") in text
        assert th.TopicCallback.unpack(markup.inline_keyboard[1][0].callback_data).a == th.UNBAN

        await th.decide(_press(), th.TopicCallback(a=th.UNBAN, id=topic.id), _fsm(), bot)

    assert not await topic_service().repository.is_banned(7)
    ctx.answer.assert_any_await(t("topics_ban_done"))


@pytest.mark.asyncio
async def test_anonymous_author_has_no_ban_button(fake_redis):
    topic = await _add(user_id=None)
    ctx = _ctx(value=str(topic.id))
    ctx.put = AsyncMock()
    ctx.answer = AsyncMock()

    await menus.menus.get_menu(th.ENTRIES_MENU).on_select(ctx)

    _text, markup = ctx.put.await_args.args
    actions = [th.TopicCallback.unpack(b.callback_data).a for row in markup.inline_keyboard[:-1] for b in row]
    assert th.BAN not in actions


@pytest.mark.asyncio
async def test_same_status_again_does_not_notify(fake_redis, bot):
    topic = await _add(status=TopicStatus.LATER)

    with patch.object(menus.menus, "context", return_value=_decide_ctx()):
        await th.decide(_press(), th.TopicCallback(a="later", id=topic.id), _fsm(), bot)

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_decision_is_ignored(fake_redis, bot):
    topic = await _add()
    ctx = _decide_ctx()

    with patch.object(menus.menus, "context", return_value=ctx):
        await th.decide(_press(), th.TopicCallback(a="new", id=topic.id), _fsm(), bot)

    assert (await topic_service().repository.get(topic.id)).status is TopicStatus.NEW
    ctx.show.assert_not_awaited()
