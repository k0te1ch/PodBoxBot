from unittest.mock import AsyncMock, patch

import pytest
from aiogram_tests.requester import Calls
from aiogram_tests.types.dataset import AUDIO, CALLBACK_QUERY, MESSAGE, USER

from config import LANGUAGES
from handlers.audio_handler import forward_yes
from services import context, keyboards


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_user"])
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize(
    "stored, expected_call",
    [
        ({"info": {"number": "600", "title": "Название эпизода"}}, True),
        (None, False),
    ],
)
async def test_forward_yes(
    callback_handler_factory,
    bot_factory,
    username,
    language,
    stored,
    expected_call,
):
    handler = callback_handler_factory(forward_yes)
    bot = await bot_factory(handler)

    user = USER.as_object(id=123, username=username, language_code=language)
    audio = AUDIO.as_object(file_id="audio_file_id")
    message = MESSAGE.as_object(
        message_id=2,
        from_user=user,
        text="Test message",
        audio=audio,
    )
    callback_query = CALLBACK_QUERY.as_object(id="3", from_user=user, message=message, data="fwd_verify_yes")

    with (
        patch("handlers.audio_handler.Bot.send_audio", new=AsyncMock()) as mock_send_audio,
        patch("handlers.audio_handler.FORWARD_CHAT_USERNAME", new="@test_group"),
        patch("handlers.audio_handler.CallbackQuery.answer", new=AsyncMock()) as mock_callback_answer,
        patch("handlers.audio_handler.pin_message", new=AsyncMock()),
        patch(
            "handlers.audio_handler.load_template_info",
            new=AsyncMock(return_value=stored),
        ) as mock_load,
        patch(
            "handlers.audio_handler.generate_podcast_text",
            return_value="Generated podcast text",
        ),
    ):
        calls: Calls = await bot.query(callback_query)

        # Template info is always looked up by the audio file name.
        mock_load.assert_called_once_with(message.audio.file_name)

        if expected_call:
            # Audio forwarded with the generated caption.
            mock_send_audio.assert_called_once_with(
                chat_id="@test_group",
                audio=audio.file_id,
                caption="Generated podcast text",
            )

            # Reply markup updated to the main audio menu.
            edit_reply_markup_call = calls.edit_message_reply_markup.fetchone()
            assert edit_reply_markup_call.reply_markup == keyboards["podcast_handler"][language].audio_menu_main

            # Success response.
            mock_callback_answer.assert_called_once_with("Переслали в чат!")
        else:
            # Nothing forwarded; user told the template info is missing.
            mock_send_audio.assert_not_called()
            mock_callback_answer.assert_called_once_with(context[language].invalid_input, show_alert=True)
