"""Настройки, запуск и кнопки раздела /admin, которые ведут в анкету и к авторам."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

import config
import main
from forms import topic_suggestion as form
from handlers import topics_list_handler as lh
from services.i18n import t
from services.metrics import bot_metrics
from services.topics import Kind


@pytest.mark.parametrize(
    ("raw", "tags"),
    [("тема", ["тема"]), ("#Тема, topic ,", ["тема", "topic"]), ("", []), (" , ", [])],
)
def test_hashtag_setting_is_a_comma_separated_list(raw, tags):
    assert config._hashtags(raw) == tags


def test_topics_are_off_by_default():
    fields = config.Settings.model_fields

    assert fields["TOPICS_ENABLED"].default is False
    assert fields["TOPICS_HOSTS_CHAT"].default is None
    assert (fields["TOPICS_HASHTAG"].default, fields["TOPICS_QUESTION_HASHTAG"].default) == ("тема", "вопрос")
    assert fields["TOPICS_ACK_REACTION"].default is True
    assert fields["TOPICS_ACK_EPHEMERAL"].default is True
    assert not [name for name in fields if name.startswith("TOPICS_POLL")]


def _list_size(kind: str) -> str:
    return f'podboxbot_topics_list_size{{bot="podboxbot",kind="{kind}"}}'


@pytest.mark.asyncio
async def test_list_size_is_reported_on_startup(fake_redis, add_item, monkeypatch):
    monkeypatch.setattr(main, "redis", fake_redis)
    await add_item("почему небо голубое?", Kind.QUESTION)

    await main.report_topics_list_size()

    rendered = bot_metrics.sdk.render().decode()
    assert f"{_list_size('question')} 1.0" in rendered
    assert f"{_list_size('topic')} 0.0" in rendered


@pytest.mark.asyncio
async def test_startup_does_not_touch_the_list_when_topics_are_off(monkeypatch):
    monkeypatch.setattr(config, "TOPICS_ENABLED", False)
    refresh = AsyncMock()
    monkeypatch.setattr(main, "refresh_list_size", refresh)

    await main.report_topics_list_size()

    refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_survives_a_broken_redis(fake_redis, monkeypatch):
    monkeypatch.setattr(main, "redis", fake_redis)
    monkeypatch.setattr(main, "refresh_list_size", AsyncMock(side_effect=ConnectionError("redis is down")))

    await main.report_topics_list_size()


def _menu_ctx(bot, state=None):
    message = MagicMock()
    message.chat.id = 1
    message.answer = AsyncMock()
    event = MagicMock()
    event.from_user.id = 1
    event.from_user.username = "admin"
    event.from_user.language_code = "ru"
    return MagicMock(
        data={"bot": bot, "state": state, "metrics": None},
        message=message,
        event=event,
        locale="ru",
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "ask"), [(Kind.TOPIC, "topics_form_ask_topic"), (Kind.QUESTION, "topics_form_ask_question")]
)
async def test_add_buttons_of_the_menu_open_the_admin_form(fake_redis, bot, kind, ask):
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=11))
    ctx = _menu_ctx(bot, state)

    await lh._add_from_menu(kind)(ctx)

    ctx.answer.assert_awaited_once_with()
    assert bot.send_message.await_args.kwargs["text"] == t(f"{ask}_admin", max=50)
    session, _ui = await form.TYPED.storage.load(state)
    assert (session.context["trusted"], session.context[form.KIND]) == (True, kind.value)


@pytest.mark.asyncio
async def test_authors_button_of_the_menu_shows_the_panel(fake_redis, add_item, bot):
    await add_item("почему небо голубое?", Kind.QUESTION)
    ctx = _menu_ctx(bot)

    await lh._authors_from_menu(ctx)

    text, markup = ctx.message.answer.await_args.args[0], ctx.message.answer.await_args.kwargs["reply_markup"]
    assert text == t("topics_authors_title")
    assert markup.inline_keyboard[0][0].text == t("topics_author", name="@listener", count=1)
