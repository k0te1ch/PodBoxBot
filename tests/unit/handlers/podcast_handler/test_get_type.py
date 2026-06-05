import pytest
from aiogram_tests.types.dataset import MESSAGE, USER

from config import LANGUAGES
from forms.upload_file import MP3, TYPE_EPISODE, upload_file_engine
from handlers.podcast_handler import get_type
from services import context, keyboards
from utils.dialog import SESSION_KEY


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_of_test"])
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("type_episode_key", ["main_episode", "episode_aftershow"])
async def test_get_type_handler(
    username,
    language,
    type_episode_key,
    handler_factory,
    bot_factory,
    state_context_factory,
    dialog_state,
    session_state_data,
):
    # Session is freshly created, sitting on the type_episode step.
    handler = handler_factory(
        get_type,
        state=dialog_state,
        state_data=session_state_data(step=TYPE_EPISODE),
    )
    bot = await bot_factory(handler)
    user = USER.as_object(username=username, language_code=language)
    msg = MESSAGE.as_object(text=context[language][type_episode_key], from_user=user)

    calls = await bot.query(message=msg)
    state_context = await state_context_factory(handler, message=msg)

    expected_type = "main" if type_episode_key == "main_episode" else "aftershow"

    # The engine stored the choice and advanced the session to the mp3 step.
    session = upload_file_engine.restore_session((await state_context.get_data())[SESSION_KEY])
    assert session.answers[TYPE_EPISODE] == expected_type
    assert upload_file_engine.current_step(session).id == MP3

    assert len(calls.send_message) == 1
    sent_message = calls.send_message.fetchone()
    # ``ask_mp3`` interpolates ``type_episode`` / ``type_episode_text`` from the
    # caller's locals (see services.context). Mirror what the handler computes
    # so the expected text matches across locales.
    type_episode = expected_type  # noqa: F841
    type_episode_text = "основной эпизод" if expected_type == "main" else "эпизод послешоу"  # noqa: F841
    assert sent_message.text == context[language].ask_mp3
    assert sent_message.reply_markup == keyboards["podcast_handler"][language].cancel
