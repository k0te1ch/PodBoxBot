import pytest
from aiogram.filters import Command
from aiogram_tests.types.dataset import MESSAGE, USER

from config import LANGUAGES
from forms.upload_file import TYPE_EPISODE, upload_file_engine
from handlers.podcast_handler import start
from services import context
from utils.dialog import SESSION_KEY


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_of_test"])
@pytest.mark.parametrize("language", LANGUAGES)
async def test_start_command(language, username, handler_factory, bot_factory, state_context_factory):
    handler = handler_factory(start, command=Command(commands=["start"]))
    bot = await bot_factory(handler)
    user = USER.as_object(username=username, language_code=language)
    msg = MESSAGE.as_object(text="/start", from_user=user)

    calls = await bot.query(message=msg)
    state_context = await state_context_factory(handler, message=msg)

    # The prompt is unchanged.
    assert len(calls.send_message) == 1
    assert calls.send_message.fetchone().text == context[language].ask_typeEpisode

    # /start now opens a dialog_engine session sitting on the first step,
    # instead of setting an aiogram FSM state.
    data = await state_context.get_data()
    assert SESSION_KEY in data, "start() should create a dialog session in FSM data"
    session = upload_file_engine.restore_session(data[SESSION_KEY])
    assert session.is_active
    assert upload_file_engine.current_step(session).id == TYPE_EPISODE
