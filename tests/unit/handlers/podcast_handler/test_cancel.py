import pytest
from aiogram.types import ReplyKeyboardRemove
from aiogram_tests.types.dataset import MESSAGE, USER

from config import LANGUAGES
from forms.upload_file import MP3
from handlers.podcast_handler import cancel
from services import context
from utils.dialog import SESSION_KEY


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_user", "test_of_test"])
@pytest.mark.parametrize("language", LANGUAGES)
async def test_cancel_command(
    language, username, handler_factory, bot_factory, state_context_factory, dialog_state, session_state_data
):
    # An upload is in progress (session on some step) when the user cancels.
    handler = handler_factory(cancel, state=dialog_state, state_data=session_state_data(step=MP3))
    bot = await bot_factory(handler)
    user = USER.as_object(username=username, language_code=language)
    msg = MESSAGE.as_object(text="Отмена", from_user=user)

    calls = await bot.query(message=msg)
    state_context = await state_context_factory(handler, message=msg)

    assert len(calls.send_message) == 1
    sent_message = calls.send_message.fetchone()
    assert sent_message.text == context[language].canceled
    assert sent_message.reply_markup == ReplyKeyboardRemove(remove_keyboard=True)

    # Cancelling wipes the dialog session and the FSM state.
    assert SESSION_KEY not in (await state_context.get_data()), "Dialog session was not cleared on cancel"
    assert (await state_context.get_state()) is None
