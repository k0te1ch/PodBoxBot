import pytest
from aiogram_tests.types.dataset import MESSAGE, USER
from app.config import LANGUAGES
from app.forms.upload_file import UploadFile
from app.handlers.podcast_handler import get_type
from app.services.context import context
from app.services.keyboards import keyboards


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_of_test"])
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("type_episode_key", ["main_episode", "aftershow_episode"])
async def test_get_type_handler(
    username,
    language,
    type_episode_key,
    handler_factory,
    bot_factory,
    state_context_factory,
):
    # Set up handler for get_type
    handler_func = get_type
    state = UploadFile.type_episode
    typeEpisode = context[language][type_episode_key]

    # Create handler, bot, and context
    handler = handler_factory(handler_func, state=state)

    bot = await bot_factory(handler)
    user = USER.as_object(username=username, language_code=language)

    # Simulate a message from the user
    msg = MESSAGE.as_object(text=typeEpisode, from_user=user)
    calls = await bot.query(message=msg)
    state_context = await state_context_factory(handler, message=msg)
    typeEpisode = typeEpisode.lower()

    # Verify FSM state update and sent message
    state_data = await state_context.get_data()
    expected_type = type_episode_key.replace("_episode", "")
    assert (
        state_data.get("typeEpisode") == expected_type
    ), "Expected typeEpisode to be set in state data"
    assert (
        await state_context.get_state()
    ) == UploadFile.mp3, "FSM state did not update to UploadFile.mp3 as expected"

    assert len(calls.send_message) == 1, "Expected one message to be sent"
    sent_message = calls.send_message.fetchone()
    expected_text = context[language].ask_mp3
    assert (
        sent_message.text == expected_text
    ), "Sent message text does not match expected text"
    assert (
        sent_message.reply_markup == keyboards["podcast_handler"][language].cancel
    ), "Keyboard does not match expected 'cancel' keyboard"
