from unittest.mock import AsyncMock, patch

import pytest
from aiogram_tests.requester import Calls
from aiogram_tests.types.dataset import AUDIO, CALLBACK_QUERY, MESSAGE, USER
from app.config import LANGUAGES
from app.handlers.audio_handler import forward_yes
from app.services import context
from app.services.keyboards import keyboards
from app.utils.validators import validate_template


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_user"])
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize(
    "template_text, expected_call",
    [
        (
            '<pre language="text">Number: 600\nTitle: Название эпизода\nComment: Описание эпизода\nTags: Окно, жесть, спина\nChapters: |\n00:00:07 - Вступление и что нового за неделю\n00:28:53 - Название темы 1\n01:40:56 - Название темы 2\n02:17:25 - Озвучили наших патронов и анонсировали послешоу</pre>',
            True,
        ),
        ("Invalid text", False),
    ],
)
async def test_forward_yes(
    callback_handler_factory,
    bot_factory,
    username,
    language,
    template_text,
    expected_call,
):
    handler = callback_handler_factory(forward_yes)
    bot = await bot_factory(handler)

    user = USER.as_object(id=123, username=username, language_code=language)
    replied_message = MESSAGE.as_object(
        message_id=1, from_user=user, text=template_text
    )
    audio = AUDIO.as_object(file_id="audio_file_id")
    message = MESSAGE.as_object(
        message_id=2,
        from_user=user,
        text="Test message",
        audio=audio,
        reply_to_message=replied_message,
    )
    callback_query = CALLBACK_QUERY.as_object(
        id="3", from_user=user, message=message, data="fwd_verify_yes"
    )

    with (
        patch(
            "handlers.audio_handler.Bot.send_audio", new=AsyncMock()
        ) as mock_send_audio,
        patch("app.handlers.audio_handler.FORWARD_CHAT_USERNAME", new="@test_group"),
        patch(
            "handlers.audio_handler.CallbackQuery.answer", new=AsyncMock()
        ) as mock_callback_answer,
        patch(
            "app.handlers.audio_handler.validate_template",
            return_value={} if expected_call else None,
        ) as mock_validate,
        patch(
            "app.handlers.audio_handler.generate_podcast_text",
            return_value="Generated podcast text",
        ) as mock_generate_text,
    ):

        calls: Calls = await bot.query(callback_query)

        if expected_call:
            # Validate `validate_template` was called with the correct input
            mock_validate.assert_called_once_with(template_text)
            # Check that `send_audio` was called with the correct parameters
            mock_send_audio.assert_called_once_with(
                chat_id="@test_group",
                audio=audio.file_id,
                caption="Generated podcast text",
            )

            # Ensure reply markup was updated correctly
            edit_reply_markup_call = calls.edit_message_reply_markup.fetchone()
            assert (
                edit_reply_markup_call.reply_markup
                == keyboards["podcast_handler"][language].audio_menu_main
            )

            # Verify success response
            mock_callback_answer.assert_called_once_with("Переслали в чат!")
        else:
            # Ensure `send_audio` was not called
            mock_send_audio.assert_not_called()

            # Verify failure response with alert
            mock_callback_answer.assert_called_once_with(
                context[language].invalid_input, show_alert=True
            )
